import os
import struct
import json
import io
import math
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

# ==============================================================================
# 1. SEAMLESS TILEABLE COTTON PBR TEXTURES (1024x1024, NEUTRAL WHITE/OFF-WHITE)
# ==============================================================================
TEX_SIZE = 1024
rng = np.random.default_rng(42)

def make_tileable_noise(size, freq, octaves=4, persistence=0.5):
    noise = np.zeros((size, size), dtype=np.float32)
    amp = 1.0
    total_amp = 0.0
    fy = np.fft.fftfreq(size) * size
    fx = np.fft.fftfreq(size) * size
    FX, FY = np.meshgrid(fx, fy)
    R = np.sqrt(FX**2 + FY**2)
    for o in range(octaves):
        f = freq * (2 ** o)
        raw = rng.standard_normal((size, size)).astype(np.float32)
        F = np.fft.fft2(raw)
        filt = np.exp(-0.5 * ((R - f) / max(1.0, f * 0.45))**2)
        filt[0, 0] = 0.0
        layer = np.real(np.fft.ifft2(F * filt))
        std = np.std(layer)
        if std > 1e-6:
            layer /= std
        noise += layer * amp
        total_amp += amp
        amp *= persistence
    return noise / total_amp

y_idx, x_idx = np.mgrid[0:TEX_SIZE, 0:TEX_SIZE].astype(np.float32)
u_tex = x_idx / TEX_SIZE
v_tex = y_idx / TEX_SIZE

wales = np.cos(2.0 * np.pi * 220.0 * u_tex)
courses = np.cos(2.0 * np.pi * 260.0 * v_tex + 0.35 * np.sin(2.0 * np.pi * 220.0 * u_tex))
knit_micro = 0.55 * wales + 0.45 * courses

heather_macro = make_tileable_noise(TEX_SIZE, freq=14, octaves=4, persistence=0.55)
heather_micro = make_tileable_noise(TEX_SIZE, freq=64, octaves=3, persistence=0.5)

height = 0.42 * knit_micro + 0.35 * heather_macro + 0.23 * heather_micro
height = (height - height.min()) / (height.max() - height.min())

albedo_val = 246.0 + 8.0 * height
albedo_rgb = np.stack([albedo_val, albedo_val, albedo_val], axis=-1).clip(0, 255).astype(np.uint8)
albedo_img = Image.fromarray(albedo_rgb)

strength = 1.25
dh_dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5 * strength
dh_dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5 * strength
nx, ny, nz = -dh_dx, -dh_dy, np.ones_like(height)
nlen = np.sqrt(nx**2 + ny**2 + nz**2)
nx /= nlen
ny /= nlen
nz /= nlen
normal_rgb = np.stack([
    (nx * 0.5 + 0.5) * 255.0,
    (ny * 0.5 + 0.5) * 255.0,
    (nz * 0.5 + 0.5) * 255.0
], axis=-1).clip(0, 255).astype(np.uint8)
normal_img = Image.fromarray(normal_rgb)

ao_chan = (241.0 + 14.0 * height).clip(0, 255).astype(np.uint8)
rough_chan = (218.0 + 22.0 * (1.0 - height)).clip(0, 255).astype(np.uint8)
metal_chan = np.zeros_like(ao_chan, dtype=np.uint8)
orm_img = Image.fromarray(np.stack([ao_chan, rough_chan, metal_chan], axis=-1))

def img_to_png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

albedo_png = img_to_png_bytes(albedo_img)
normal_png = img_to_png_bytes(normal_img)
orm_png = img_to_png_bytes(orm_img)

# ==============================================================================
# 2. PARAMETRIC GARMENT BODY AND SHARED SLEEVE MESH
# ==============================================================================
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def build_cut_glb(cfg, output_path):
    H = cfg["H"]
    y_bot = -0.5 * H
    y_top_back = +0.5 * H
    neck_drop = cfg["neck_front_drop"]

    N_THETA = 96
    N_Y = 64

    ARM_HALF_W = 8
    IY_ARM_BOT = cfg["iy_arm_bot"]
    IY_ARM_TOP = cfg["iy_arm_top"]

    def get_armhole_loop_indices(side):
        it_c = 24 if side > 0 else 72
        pts = []
        for k in range(0, ARM_HALF_W):
            pts.append((IY_ARM_TOP, it_c - side * k))
        for iy in range(IY_ARM_TOP, IY_ARM_BOT, -1):
            pts.append((iy, it_c - side * ARM_HALF_W))
        for k in range(-ARM_HALF_W, ARM_HALF_W):
            pts.append((IY_ARM_BOT, it_c + side * k))
        for iy in range(IY_ARM_BOT, IY_ARM_TOP):
            pts.append((iy, it_c + side * ARM_HALF_W))
        for k in range(ARM_HALF_W, 0, -1):
            pts.append((IY_ARM_TOP, it_c + side * k))
        return pts

    loop_pos_coords = get_armhole_loop_indices(+1)
    loop_neg_coords = get_armhole_loop_indices(-1)
    N_ARM_LOOP = len(loop_pos_coords)

    armhole_boundary = set(loop_pos_coords + loop_neg_coords)

    def is_interior_armhole(iy, it):
        if IY_ARM_BOT < iy < IY_ARM_TOP:
            if (24 - ARM_HALF_W) < it < (24 + ARM_HALF_W):
                return True
            if (72 - ARM_HALF_W) < it < (72 + ARM_HALF_W):
                return True
        return False

    thetas = np.linspace(0.0, 2.0 * np.pi, N_THETA + 1)
    sin_t = np.sin(thetas)
    cos_t = np.cos(thetas)
    s_vals = np.linspace(0.0, 1.0, N_Y + 1)

    v_arm_top = float(np.clip((cfg["y_arm_top"] - y_bot) / H, 0.70, 0.96))

    def eval_torso_dims(v):
        u_sh = np.clip((v - v_arm_top) / max(1.0 - v_arm_top, 1e-4), 0.0, 1.0)
        rx = np.where(
            v < 0.30,
            cfg["rx_hem"] + (cfg["rx_waist"] - cfg["rx_hem"]) * np.sin((v / 0.30) * (np.pi * 0.5)),
            np.where(
                v < 0.62,
                cfg["rx_waist"] + (cfg["rx_chest"] - cfg["rx_waist"]) * smoothstep(0.30, 0.62, v),
                np.where(
                    v < v_arm_top,
                    cfg["rx_chest"] + (cfg["rx_shoulder"] - cfg["rx_chest"]) * smoothstep(0.62, v_arm_top, v),
                    cfg["rx_shoulder"] + (cfg["rx_neck"] - cfg["rx_shoulder"]) * (u_sh ** 1.06)
                )
            )
        )
        rz_f = (
            cfg["rz_front"]
            + 0.018 * np.exp(-((v - 0.66) / 0.22)**2)
            + 0.004 * np.exp(-((v - 0.35) / 0.25)**2)
            - 0.014 * smoothstep(v_arm_top, 1.0, v)
        )
        rz_b = (
            cfg["rz_back"]
            + 0.016 * np.exp(-((v - 0.70) / 0.20)**2)
            - 0.003 * np.exp(-((v - 0.30) / 0.18)**2)
            - 0.012 * smoothstep(v_arm_top, 1.0, v)
        )
        zc = 0.003 * np.sin((v - 0.4) * np.pi)
        return rx, rz_f, rz_b, zc

    def eval_torso_point(y, theta):
        st = math.sin(theta)
        ct = math.cos(theta)
        s = float(np.clip((y - y_bot) / H, 0.0, 1.0))
        sh_env = smoothstep(0.58, s_arm_top, s) * (1.0 - smoothstep(s_arm_top, 1.0, s))
        y -= cfg["shoulder_slope_drop"] * (abs(st) ** 1.6) * sh_env
        v_norm = float(np.clip((y - y_bot) / H, 0.0, 1.0))
        rx, rz_f, rz_b, zc = eval_torso_dims(v_norm)
        rz = rz_f if ct >= 0.0 else rz_b
        p = cfg["superellipse_p"]
        denom = (abs(st) ** p + abs(ct) ** p) ** (1.0 / p)
        x_base = rx * st / denom
        z_base = zc + rz * ct / denom
        collar_blend = smoothstep(0.92, 1.0, s)
        x_neck = cfg["rx_neck"] * st
        z_neck = 0.003 + cfg["rz_neck"] * ct
        return np.array([
            (1.0 - collar_blend) * x_base + collar_blend * x_neck,
            y,
            (1.0 - collar_blend) * z_base + collar_blend * z_neck
        ], dtype=np.float64)

    verts = []
    uvs = []
    grid_idx = np.full((N_Y + 1, N_THETA + 1), -1, dtype=np.int32)
    s_arm_top = IY_ARM_TOP / float(N_Y)

    for iy, s in enumerate(s_vals):
        for it, th in enumerate(thetas):
            if is_interior_armhole(iy, it):
                continue

            st = sin_t[it]
            ct = cos_t[it]
            front_w = (0.5 * (1.0 + ct)) ** 1.75
            y_neck_th = y_top_back - neck_drop * front_w

            hem_sag = cfg["hem_curve"] * (1.0 - s)**3 * (ct**2)
            y = y_bot + s * (y_neck_th - y_bot) + hem_sag

            sh_env = smoothstep(0.58, s_arm_top, s) * (1.0 - smoothstep(s_arm_top, 1.0, s))
            y -= cfg["shoulder_slope_drop"] * (abs(st) ** 1.6) * sh_env

            v_norm = float(np.clip((y - y_bot) / H, 0.0, 1.0))
            rx, rz_f, rz_b, zc = eval_torso_dims(v_norm)
            rz = rz_f if ct >= 0.0 else rz_b

            p = cfg["superellipse_p"]
            denom = (np.abs(st)**p + np.abs(ct)**p) ** (1.0 / p)
            x_base = rx * (st / denom)
            z_base = zc + rz * (ct / denom)

            collar_blend = smoothstep(0.92, 1.0, s)
            x_neck = cfg["rx_neck"] * st
            z_neck = 0.003 + cfg["rz_neck"] * ct

            x = (1.0 - collar_blend) * x_base + collar_blend * x_neck
            z = (1.0 - collar_blend) * z_base + collar_blend * z_neck

            chest_flat = 1.0 - 0.90 * np.exp(-((st / 0.50)**2 + ((s - 0.65) / 0.24)**2))
            fa = cfg["fold_amp"]
            underarm_fold = fa * np.sin(6.0 * th + 2.4 * s) * np.exp(-((s - 0.48) / 0.22)**2) * (np.abs(st)**1.5)
            lower_drape = (fa * 0.85) * np.sin(5.0 * th - 1.7 * s) * ((1.0 - s)**1.15) * chest_flat
            hem_stitch = 0.0009 * np.exp(-((s - 0.024) / 0.009)**2)
            disp = underarm_fold + lower_drape + hem_stitch
            x += disp * st
            z += disp * ct

            side = 1.0 if st >= 0.0 else -1.0
            it_c = 24 if side > 0 else 72
            dit = -side * (it - it_c) / ARM_HALF_W
            diy = (iy - 0.5 * (IY_ARM_BOT + IY_ARM_TOP)) / (0.5 * (IY_ARM_TOP - IY_ARM_BOT))
            box_r = max(abs(dit), abs(diy))
            if 1.0 <= box_r < 1.55:
                angle = math.atan2(dit, diy)
                c_p = math.cos(angle)
                s_p = math.sin(angle)
                ring_y = 0.5 * (cfg["y_arm_top"] + cfg["y_arm_bot"]) + (
                    0.5 * (cfg["y_arm_top"] - cfg["y_arm_bot"]) * c_p * box_r
                )
                theta_center = thetas[it_c]
                theta_span = ARM_HALF_W * (2.0 * math.pi / N_THETA)
                ring_theta = theta_center - side * theta_span * s_p * box_r
                ring_point = eval_torso_point(ring_y, ring_theta)
                blend = smoothstep(1.55, 1.0, box_r)
                x = (1.0 - blend) * x + blend * ring_point[0]
                y = (1.0 - blend) * y + blend * ring_point[1]
                z = (1.0 - blend) * z + blend * ring_point[2]

            grid_idx[iy, it] = len(verts)
            verts.append([x, y, z])

            u_norm = 0.25 if it == N_THETA else ((it / N_THETA + 0.25) % 1.0)
            u_coord = 0.02 + 0.96 * u_norm
            v_coord = 0.05 + 0.58 * s
            uvs.append([u_coord, v_coord])

    faces = []
    for iy in range(N_Y):
        for it in range(N_THETA):
            v00 = grid_idx[iy, it]
            v10 = grid_idx[iy, it + 1]
            v11 = grid_idx[iy + 1, it + 1]
            v01 = grid_idx[iy + 1, it]
            if v00 < 0 or v10 < 0 or v11 < 0 or v01 < 0:
                continue
            b00 = (iy, it) in armhole_boundary
            b10 = (iy, it + 1) in armhole_boundary
            b11 = (iy + 1, it + 1) in armhole_boundary
            b01 = (iy + 1, it) in armhole_boundary
            if (b00 and b10 and b11) or (b00 and b01 and b11):
                faces.append([v00, v10, v01])
                faces.append([v10, v11, v01])
            else:
                faces.append([v00, v10, v11])
                faces.append([v00, v11, v01])

    # ==========================================================================
    # COLLAR
    # ==========================================================================
    collar_profile = [
        ( 0.0000,  0.0000, 0.642),
        ( 0.0012,  0.0024, 0.654),
        (-0.0002,  0.0062, 0.666),
        (-0.0024,  0.0088, 0.678),
        (-0.0050,  0.0096, 0.688),
        (-0.0072,  0.0076, 0.698),
        (-0.0080,  0.0010, 0.712),
        (-0.0074, -0.0120, 0.732),
        (-0.0062, -0.0360, 0.762),
    ]
    collar_grid = np.zeros((len(collar_profile), N_THETA + 1), dtype=np.int32)
    collar_grid[0, :] = grid_idx[N_Y, :]

    for ip in range(1, len(collar_profile)):
        r_off, y_off, v_c = collar_profile[ip]
        for it, th in enumerate(thetas):
            base_v = verts[grid_idx[N_Y, it]]
            st = sin_t[it]
            ct = cos_t[it]
            rib = 0.00032 * np.cos(80.0 * th) if ip <= 4 else 0.0
            x = base_v[0] + (r_off + rib) * st
            z = base_v[2] + (r_off + rib) * ct
            y_scale = 1.0 if ip <= 6 else (0.55 + 0.45 * (0.5 * (1.0 - ct)))
            y = base_v[1] + y_off * y_scale
            collar_grid[ip, it] = len(verts)
            verts.append([x, y, z])
            u_norm = 0.25 if it == N_THETA else ((it / N_THETA + 0.25) % 1.0)
            uvs.append([0.02 + 0.96 * u_norm, v_c])

    for ip in range(len(collar_profile) - 1):
        for it in range(N_THETA):
            v00 = collar_grid[ip, it]
            v10 = collar_grid[ip, it + 1]
            v11 = collar_grid[ip + 1, it + 1]
            v01 = collar_grid[ip + 1, it]
            faces.append([v00, v10, v11])
            faces.append([v00, v11, v01])

    # ==========================================================================
    # HEM
    # ==========================================================================
    hem_profile = [
        (-0.0024, -0.0010, 0.042),
        (-0.0042,  0.0040, 0.030),
        (-0.0038,  0.0220, 0.012),
    ]
    hem_grid = np.zeros((len(hem_profile) + 1, N_THETA + 1), dtype=np.int32)
    hem_grid[0, :] = grid_idx[0, :]

    for ih, (r_off, y_off, v_h) in enumerate(hem_profile):
        for it, th in enumerate(thetas):
            base_v = verts[grid_idx[0, it]]
            x = base_v[0] + r_off * sin_t[it]
            z = base_v[2] + r_off * cos_t[it]
            y = base_v[1] + y_off
            hem_grid[ih + 1, it] = len(verts)
            verts.append([x, y, z])
            u_norm = 0.25 if it == N_THETA else ((it / N_THETA + 0.25) % 1.0)
            uvs.append([0.02 + 0.96 * u_norm, v_h])

    for ih in range(len(hem_profile)):
        for it in range(N_THETA):
            v00 = hem_grid[ih, it]
            v10 = hem_grid[ih + 1, it]
            v11 = hem_grid[ih + 1, it + 1]
            v01 = hem_grid[ih, it + 1]
            faces.append([v00, v10, v11])
            faces.append([v00, v11, v01])

    # ==========================================================================
    # SLEEVES (Seamless Mesh Connection, Exact Vertices Shared)
    # ==========================================================================
    N_LEN = 32
    sleeve_configs = [
        (+1.0, loop_pos_coords, 0.04, 0.46),
        (-1.0, loop_neg_coords, 0.54, 0.96),
    ]

    for side, loop_coords, u_min, u_max in sleeve_configs:
        root_indices = [grid_idx[iy, it] for (iy, it) in loop_coords]
        root_indices_closed = root_indices + [root_indices[0]]

        root_pts = np.array([verts[i] for i in root_indices], dtype=np.float64)
        root_pts_closed = np.vstack([root_pts, root_pts[0:1]])
        it_center = 24 if side > 0 else 72
        iy_center = 0.5 * (IY_ARM_BOT + IY_ARM_TOP)
        iy_radius = 0.5 * (IY_ARM_TOP - IY_ARM_BOT)
        root_tangents = []
        for (iy, it), p_root in zip(loop_coords, root_pts):
            outside_points = []
            for iy_step, it_step in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                next_iy, next_it = iy + iy_step, it + it_step
                if not (0 <= next_iy <= N_Y and 0 <= next_it <= N_THETA):
                    continue
                if grid_idx[next_iy, next_it] < 0:
                    continue
                next_diy = (next_iy - iy_center) / iy_radius
                next_dit = -side * (next_it - it_center) / ARM_HALF_W
                if max(abs(next_diy), abs(next_dit)) > 1.0:
                    outside_points.append(np.array(verts[grid_idx[next_iy, next_it]]))
            tangent = p_root - np.mean(outside_points, axis=0) if outside_points else np.array([side, 0.0, 0.0])
            tangent /= max(np.linalg.norm(tangent), 1e-8)
            root_tangents.append(tangent)

        root_center = root_pts.mean(axis=0)

        hang_angle = math.radians(cfg["sleeve_hang_deg"])
        sleeve_axis = np.array([side * math.sin(hang_angle), -math.cos(hang_angle), 0.0], dtype=np.float64)
        
        u_vec = np.array([side * math.cos(hang_angle), math.sin(hang_angle), 0.0], dtype=np.float64)
        v_vec = np.array([0.0, 0.0, 1.0], dtype=np.float64)

        sleeve_len = cfg["sleeve_len"]
        cuff_center = root_center + sleeve_axis * sleeve_len

        r_cuff_u = cfg["r_cuff_u"]
        r_cuff_v = cfg["r_cuff_v"]

        s_vals_sl = np.linspace(0.0, 1.0, N_LEN + 1)
        s_grid = np.zeros((N_LEN + 1, N_ARM_LOOP + 1), dtype=np.int32)

        for il, s in enumerate(s_vals_sl):
            for ir in range(N_ARM_LOOP + 1):
                if il == 0:
                    # EXACT WELDING: Use the pre-existing torso vertex index
                    s_grid[il, ir] = root_indices_closed[ir]
                else:
                    phi = 2.0 * math.pi * (ir / N_ARM_LOOP)
                    c_p = math.cos(phi)  
                    s_p = math.sin(phi)  

                    p_root = root_pts_closed[ir]
                    p_cuff = cuff_center + (c_p * r_cuff_u) * u_vec + (s_p * r_cuff_v) * v_vec

                    chord_vec = p_cuff - p_root
                    chord_len = np.linalg.norm(chord_vec)
                    
                    t0_dir = 0.25 * root_tangents[ir % N_ARM_LOOP] + 0.75 * sleeve_axis
                    t0_dir /= max(np.linalg.norm(t0_dir), 1e-8)
                    if np.dot(t0_dir, chord_vec) < 0.0:
                        t0_dir = -t0_dir
                    t0 = t0_dir * (chord_len * 0.30)
                    t1 = sleeve_axis * (chord_len * 0.40)

                    s2 = s * s
                    s3 = s2 * s
                    h00 = 2.0 * s3 - 3.0 * s2 + 1.0
                    h10 = s3 - 2.0 * s2 + s
                    h01 = -2.0 * s3 + 3.0 * s2
                    h11 = s3 - s2

                    pos = h00 * p_root + h10 * t0 + h01 * p_cuff + h11 * t1

                    underarm_fold = (cfg["fold_amp"] * 0.85) * math.sin(5.0 * phi + 2.6 * s) * (max(0.0, -c_p) ** 1.5) * math.sin(s * math.pi)
                    cuff_stitch = 0.0008 * math.exp(-((s - 0.91) / 0.022)**2)

                    disp = underarm_fold + cuff_stitch
                    pos += disp * (c_p * u_vec + s_p * v_vec)

                    s_grid[il, ir] = len(verts)
                    verts.append(pos.tolist())

                    u_coord = u_min + (u_max - u_min) * (ir / N_ARM_LOOP)
                    v_coord = 0.785 + 0.175 * s
                    uvs.append([u_coord, v_coord])

        for il in range(N_LEN):
            for ir in range(N_ARM_LOOP):
                v00 = s_grid[il, ir]
                v10 = s_grid[il + 1, ir]
                v11 = s_grid[il + 1, ir + 1]
                v01 = s_grid[il, ir + 1]
                p00 = np.array(verts[v00])
                p10 = np.array(verts[v10])
                p01 = np.array(verts[v01])
                fn = np.cross(p10 - p00, p01 - p00)
                out_dir = p00 - ((1.0 - s_vals_sl[il]) * root_center + s_vals_sl[il] * cuff_center)
                if np.dot(fn, out_dir) >= 0:
                    faces.append([v00, v10, v11])
                    faces.append([v00, v11, v01])
                else:
                    faces.append([v00, v11, v10])
                    faces.append([v00, v01, v11])

        cuff_lip = [
            (-0.0022,  0.002, 0.968),
            (-0.0038, -0.015, 0.985),
        ]
        lip_grid = np.zeros((len(cuff_lip) + 1, N_ARM_LOOP + 1), dtype=np.int32)
        lip_grid[0, :] = s_grid[N_LEN, :]

        for ic, (r_in, ax_back, v_l) in enumerate(cuff_lip):
            for ir in range(N_ARM_LOOP + 1):
                phi = 2.0 * math.pi * (ir / N_ARM_LOOP)
                c_p = math.cos(phi)
                s_p = math.sin(phi)
                base_v = np.array(verts[s_grid[N_LEN, ir]])
                pos_l = base_v + r_in * (c_p * u_vec + s_p * v_vec) + ax_back * sleeve_axis
                lip_grid[ic + 1, ir] = len(verts)
                verts.append(pos_l.tolist())
                u_coord = u_min + (u_max - u_min) * (ir / N_ARM_LOOP)
                uvs.append([u_coord, v_l])

        for ic in range(len(cuff_lip)):
            for ir in range(N_ARM_LOOP):
                v00 = lip_grid[ic, ir]
                v10 = lip_grid[ic + 1, ir]
                v11 = lip_grid[ic + 1, ir + 1]
                v01 = lip_grid[ic, ir + 1]
                p00 = np.array(verts[v00])
                p10 = np.array(verts[v10])
                p01 = np.array(verts[v01])
                fn = np.cross(p10 - p00, p01 - p00)
                in_dir = cuff_center - p00
                if np.dot(fn, in_dir) >= 0:
                    faces.append([v00, v10, v11])
                    faces.append([v00, v11, v01])
                else:
                    faces.append([v00, v11, v10])
                    faces.append([v00, v01, v11])

    verts = np.array(verts, dtype=np.float32)
    uvs = np.array(uvs, dtype=np.float32)
    faces = np.array(faces, dtype=np.uint32)

    vmin = verts.min(axis=0)
    vmax = verts.max(axis=0)
    verts -= 0.5 * (vmin + vmax)
    vmin = verts.min(axis=0)
    vmax = verts.max(axis=0)

    # Clean smooth normals - NO internal duplication or unmerged boundaries
    normals = np.zeros_like(verts, dtype=np.float64)
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    np.add.at(normals, faces[:, 0], fn)
    np.add.at(normals, faces[:, 1], fn)
    np.add.at(normals, faces[:, 2], fn)

    pos_keys = np.round(verts * 100000.0).astype(np.int64)
    _, inv_idx = np.unique(pos_keys, axis=0, return_inverse=True)
    grouped_normals = np.zeros((inv_idx.max() + 1, 3), dtype=np.float64)
    np.add.at(grouped_normals, inv_idx, normals)
    normals = grouped_normals[inv_idx]
    n_len = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = (normals / np.maximum(n_len, 1e-12)).astype(np.float32)

    tan1 = np.zeros_like(verts, dtype=np.float64)
    tan2 = np.zeros_like(verts, dtype=np.float64)
    uv0 = uvs[faces[:, 0]]
    uv1 = uvs[faces[:, 1]]
    uv2 = uvs[faces[:, 2]]
    e1 = v1 - v0
    e2 = v2 - v0
    du1 = uv1[:, 0] - uv0[:, 0]
    dv1 = uv1[:, 1] - uv0[:, 1]
    du2 = uv2[:, 0] - uv0[:, 0]
    dv2 = uv2[:, 1] - uv0[:, 1]
    det = du1 * dv2 - du2 * dv1
    inv_det = np.zeros_like(det)
    np.divide(1.0, det, out=inv_det, where=np.abs(det) > 1e-12)
    inv_det = inv_det[:, None]
    sdir = (dv2[:, None] * e1 - dv1[:, None] * e2) * inv_det
    tdir = (du1[:, None] * e2 - du2[:, None] * e1) * inv_det
    np.add.at(tan1, faces[:, 0], sdir)
    np.add.at(tan1, faces[:, 1], sdir)
    np.add.at(tan1, faces[:, 2], sdir)
    np.add.at(tan2, faces[:, 0], tdir)
    np.add.at(tan2, faces[:, 1], tdir)
    np.add.at(tan2, faces[:, 2], tdir)

    n_dot_t = np.sum(normals * tan1, axis=1, keepdims=True)
    t_ortho = tan1 - normals * n_dot_t
    t_len = np.linalg.norm(t_ortho, axis=1, keepdims=True)
    fallback = np.cross(normals, np.array([[0.0, 1.0, 0.0]], dtype=np.float32))
    fb_len = np.linalg.norm(fallback, axis=1, keepdims=True)
    fallback = np.where(fb_len > 1e-6, fallback / np.maximum(fb_len, 1e-12), np.array([[1.0, 0.0, 0.0]], dtype=np.float32))
    t_unit = np.where(t_len > 1e-8, t_ortho / np.maximum(t_len, 1e-12), fallback)
    w_sign = np.where(np.sum(np.cross(normals, t_unit) * tan2, axis=1, keepdims=True) < 0.0, -1.0, 1.0)
    tangents = np.concatenate([t_unit, w_sign], axis=1).astype(np.float32)

    # Export GLB 2.0
    def pad4(b, pad_byte=b"\x00"):
        rem = len(b) % 4
        return b + pad_byte * ((4 - rem) % 4) if rem else b

    bin_chunks = []
    buffer_views = []
    def add_bv(data_bytes, target=None):
        offset = sum(len(c) for c in bin_chunks)
        bin_chunks.append(pad4(data_bytes, b"\x00"))
        bv = {"buffer": 0, "byteOffset": offset, "byteLength": len(data_bytes)}
        if target is not None:
            bv["target"] = target
        idx = len(buffer_views)
        buffer_views.append(bv)
        return idx

    bv_pos = add_bv(verts.tobytes(), target=34962)
    bv_norm = add_bv(normals.tobytes(), target=34962)
    bv_tan = add_bv(tangents.tobytes(), target=34962)
    bv_uv = add_bv(uvs.tobytes(), target=34962)
    indices_u16 = faces.astype(np.uint16)
    bv_idx = add_bv(indices_u16.tobytes(), target=34963)
    bv_albedo = add_bv(albedo_png)
    bv_normal = add_bv(normal_png)
    bv_orm = add_bv(orm_png)

    bin_blob = b"".join(bin_chunks)
    tex_transform = {"KHR_texture_transform": {"scale": [4.0, 4.0]}}

    gltf = {
        "asset": {"version": "2.0", "generator": "ClubHouse 3D Apparel Studio"},
        "extensionsUsed": ["KHR_texture_transform"],
        "scene": 0,
        "scenes": [{"name": cfg["scene_name"], "nodes": [0]}],
        "nodes": [{"name": cfg["node_name"], "mesh": 0}],
        "meshes": [
            {
                "name": cfg["mesh_name"],
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 0,
                            "NORMAL": 1,
                            "TANGENT": 2,
                            "TEXCOORD_0": 3
                        },
                        "indices": 4,
                        "material": 0,
                        "mode": 4
                    }
                ]
            }
        ],
        "materials": [
            {
                "name": "Fabric",
                "doubleSided": True,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                    "baseColorTexture": {"index": 0, "texCoord": 0, "extensions": tex_transform},
                    "metallicFactor": 0.0,
                    "roughnessFactor": 1.0,
                    "metallicRoughnessTexture": {"index": 2, "texCoord": 0, "extensions": tex_transform}
                },
                "normalTexture": {"index": 1, "texCoord": 0, "scale": 0.80, "extensions": tex_transform},
                "occlusionTexture": {"index": 2, "texCoord": 0, "strength": 0.40, "extensions": tex_transform}
            }
        ],
        "textures": [
            {"sampler": 0, "source": 0, "name": "Cotton_BaseColor"},
            {"sampler": 0, "source": 1, "name": "Cotton_Normal"},
            {"sampler": 0, "source": 2, "name": "Cotton_ORM"}
        ],
        "images": [
            {"bufferView": bv_albedo, "mimeType": "image/png", "name": "Cotton_BaseColor"},
            {"bufferView": bv_normal, "mimeType": "image/png", "name": "Cotton_Normal"},
            {"bufferView": bv_orm, "mimeType": "image/png", "name": "Cotton_ORM"}
        ],
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "accessors": [
            {"bufferView": bv_pos, "byteOffset": 0, "componentType": 5126, "count": len(verts), "type": "VEC3", "min": vmin.tolist(), "max": vmax.tolist()},
            {"bufferView": bv_norm, "byteOffset": 0, "componentType": 5126, "count": len(normals), "type": "VEC3"},
            {"bufferView": bv_tan, "byteOffset": 0, "componentType": 5126, "count": len(tangents), "type": "VEC4"},
            {"bufferView": bv_uv, "byteOffset": 0, "componentType": 5126, "count": len(uvs), "type": "VEC2"},
            {"bufferView": bv_idx, "byteOffset": 0, "componentType": 5123, "count": indices_u16.size, "type": "SCALAR"}
        ],
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(bin_blob)}]
    }

    json_bytes = pad4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), b" ")
    total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_blob)
    with open(output_path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total_length))
        f.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
        f.write(json_bytes)
        f.write(struct.pack("<II", len(bin_blob), 0x004E4942))
        f.write(bin_blob)

    dims = vmax - vmin
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[{output_path}] Tris={len(faces)}, Verts={len(verts)}, Size={size_mb:.2f}MB, Dims(W,H,D)={dims.round(4)}")
    return verts, normals, uvs, faces, dims

cuts = {
    # 1. REGULAR FIT
    "regular_tshirt.glb": {
        "scene_name": "RegularTShirtScene",
        "node_name": "RegularTShirt",
        "mesh_name": "RegularTShirtMesh",
        "H": 0.720,
        "rx_hem": 0.244,
        "rx_waist": 0.232,
        "rx_chest": 0.240,
        "rx_shoulder": 0.214,
        "shoulder_slope_drop": 0.012,
        "rx_neck": 0.097,
        "rz_neck": 0.092,
        "neck_front_drop": 0.075,
        "rz_front": 0.100,
        "rz_back": 0.098,
        "hem_curve": -0.004,
        "superellipse_p": 2.20,
        "iy_arm_bot": 40,
        "iy_arm_top": 58,
        "y_arm_bot": 0.078,
        "y_arm_top": 0.284,
        "sleeve_hang_deg": 13.5,
        "sleeve_len": 0.170,     
        "r_cuff_u": 0.068,
        "r_cuff_v": 0.070,
        "fold_amp": 0.0018,
    },

    # 2. OVERSIZE FIT
    "oversize_tshirt.glb": {
        "scene_name": "OversizeTShirtScene",
        "node_name": "OversizeTShirt",
        "mesh_name": "OversizeTShirtMesh",
        "H": 0.780,
        "rx_hem": 0.278,
        "rx_waist": 0.278,
        "rx_chest": 0.284,
        "rx_shoulder": 0.260,
        "shoulder_slope_drop": 0.015,
        "rx_neck": 0.098,
        "rz_neck": 0.093,
        "neck_front_drop": 0.070,
        "rz_front": 0.114,
        "rz_back": 0.112,
        "hem_curve": -0.003,
        "superellipse_p": 2.34,
        "iy_arm_bot": 36,
        "iy_arm_top": 56,
        "y_arm_bot": 0.038,
        "y_arm_top": 0.278,
        "sleeve_hang_deg": 14.5,
        "sleeve_len": 0.230,
        "r_cuff_u": 0.085,
        "r_cuff_v": 0.088,
        "fold_amp": 0.0028,
    },

    # 3. BOXY FIT
    "boxy_tshirt.glb": {
        "scene_name": "BoxyTShirtScene",
        "node_name": "BoxyTShirt",
        "mesh_name": "BoxyTShirtMesh",
        "H": 0.615,              
        "rx_hem": 0.292,
        "rx_waist": 0.290,
        "rx_chest": 0.294,
        "rx_shoulder": 0.270,
        "shoulder_slope_drop": 0.014,
        "rx_neck": 0.098,
        "rz_neck": 0.093,
        "neck_front_drop": 0.068,
        "rz_front": 0.112,
        "rz_back": 0.110,
        "hem_curve": 0.003,
        "superellipse_p": 2.45,
        "iy_arm_bot": 32,
        "iy_arm_top": 55,
        "y_arm_bot": -0.016,
        "y_arm_top": 0.214,
        "sleeve_hang_deg": 22.0,  
        "sleeve_len": 0.190,
        "r_cuff_u": 0.095,
        "r_cuff_v": 0.092,
        "fold_amp": 0.0024,
    },
}

ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.environ.get(
    "CLUBHOUSE_MODEL_DIR",
    ROOT_DIR / "assets" / "images" / "PAGINA WEB" / "shirts" / "models"
))
MODEL_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_PATH = Path(os.environ.get(
    "CLUBHOUSE_PREVIEW_PATH",
    Path(__file__).resolve().parent / "turntable_inspection_v7.png"
))
ZIP_PATH = Path(os.environ.get(
    "CLUBHOUSE_ARCHIVE_PATH",
    Path(__file__).resolve().parent / "clubhouse_tshirts_v7.zip"
))

built = {}
for fname, cfg in cuts.items():
    built[fname] = build_cut_glb(cfg, MODEL_DIR / fname)

# Render turntable
def render_mesh_view(verts, normals, faces, yaw_deg=0.0, pitch_deg=5.0, img_size=420, scale_px=400.0):
    yaw = np.radians(yaw_deg)
    pitch = np.radians(pitch_deg)
    cy, sy = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]], dtype=np.float32)
    R = Rx @ Ry

    v_rot = verts @ R.T
    n_rot = normals @ R.T

    cx_img = img_size * 0.5
    cy_img = img_size * 0.52
    sx = cx_img + v_rot[:, 0] * scale_px
    sy_scr = cy_img - v_rot[:, 1] * scale_px
    sz = v_rot[:, 2]

    i0, i1, i2 = faces[:, 0], faces[:, 1], faces[:, 2]
    x0, y0, z0 = sx[i0], sy_scr[i0], sz[i0]
    x1, y1, z1 = sx[i1], sy_scr[i1], sz[i1]
    x2, y2, z2 = sx[i2], sy_scr[i2], sz[i2]

    area = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
    valid = np.abs(area) > 1e-4

    L_key = np.array([-0.35, 0.65, 0.68], dtype=np.float32); L_key /= np.linalg.norm(L_key)
    L_fill = np.array([0.55, 0.25, 0.79], dtype=np.float32); L_fill /= np.linalg.norm(L_fill)
    L_rim = np.array([0.0, 0.55, -0.83], dtype=np.float32); L_rim /= np.linalg.norm(L_rim)

    n_face = n_rot[i0] + n_rot[i1] + n_rot[i2]
    n_face /= np.maximum(np.linalg.norm(n_face, axis=1, keepdims=True), 1e-8)
    flip = np.where(area < 0, -1.0, 1.0)[:, None]
    n_eff = n_face * flip

    diff_key = np.maximum(0.0, n_eff @ L_key)
    diff_fill = np.maximum(0.0, n_eff @ L_fill)
    diff_rim = np.maximum(0.0, n_eff @ L_rim)

    interior_tint = np.where(area < 0, 0.74, 1.0)
    lum = np.clip(interior_tint * (0.28 + 0.50 * diff_key + 0.20 * diff_fill + 0.14 * diff_rim), 0.0, 1.0)

    z_avg = (z0 + z1 + z2) / 3.0
    order = np.argsort(z_avg)

    img = Image.new("RGB", (img_size, img_size), (236, 238, 241))
    draw = ImageDraw.Draw(img)

    for idx in order:
        if not valid[idx]:
            continue
        c = int(lum[idx] * 246)
        poly = [(float(x0[idx]), float(y0[idx])), (float(x1[idx]), float(y1[idx])), (float(x2[idx]), float(y2[idx]))]
        draw.polygon(poly, fill=(c, c, int(min(255, c * 1.01))))
    return img

rows_imgs = []
for fname in ["regular_tshirt.glb", "oversize_tshirt.glb", "boxy_tshirt.glb"]:
    verts, normals, uvs, faces, dims = built[fname]
    views = []
    for label, yaw in [("Frente (+Z)", 0.0), ("3/4 (38°)", 38.0), ("Perfil (+X)", 90.0), ("Espalda (-Z)", 180.0)]:
        im = render_mesh_view(verts, normals, faces, yaw_deg=yaw, pitch_deg=5.0, img_size=420, scale_px=400.0)
        d = ImageDraw.Draw(im)
        d.text((12, 10), f"{fname.replace('_tshirt.glb','').upper()} - {label}", fill=(30, 35, 45))
        views.append(im)
    row = Image.new("RGB", (420 * 4, 420))
    for i, v in enumerate(views):
        row.paste(v, (i * 420, 0))
    rows_imgs.append(row)

grid = Image.new("RGB", (420 * 4, 420 * 3))
for r_i, r_im in enumerate(rows_imgs):
    grid.paste(r_im, (0, r_i * 420))

grid.save(PREVIEW_PATH)

with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
    for fname in cuts:
        zf.write(MODEL_DIR / fname, arcname=fname)
    
print(f"Done. Saved preview to {PREVIEW_PATH} and archive to {ZIP_PATH}")