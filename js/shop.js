const PRICE = 60000;
const MAX_UPLOAD_SIZE = 8 * 1024 * 1024;
const ASSET_PATHS = {
    shirts: 'assets/images/PAGINA%20WEB/shirts/reference/',
    models: 'assets/images/PAGINA%20WEB/shirts/models/',
    clubs: 'assets/images/PAGINA%20WEB/clubs/',
    icons: 'assets/images/PAGINA%20WEB/characters/icons/'
};

const fitAssets = {
    regular: `${ASSET_PATHS.shirts}REMERA%20-%20BASICA.png`,
    oversize: `${ASSET_PATHS.shirts}REMERA%20-%20OVERSIZE.png`,
    boxy: `${ASSET_PATHS.shirts}REMERA%20-%20BOXI.png`
};

const fitModels = {
    regular: {
        src: `${ASSET_PATHS.models}regular_tshirt.glb`,
        chestPosition: '0.09m 0.12m 0.12m',
        backChestPosition: '0m 0.12m -0.12m',
        sleevePosition: '-0.29m -0.02m 0.02m'
    },
    oversize: {
        src: `${ASSET_PATHS.models}oversize_tshirt.glb`,
        chestPosition: '0.09m 0.12m 0.13m',
        backChestPosition: '0m 0.12m -0.13m',
        sleevePosition: '-0.38m -0.03m 0.02m'
    },
    boxy: {
        src: `${ASSET_PATHS.models}boxy_tshirt.glb`,
        chestPosition: '0.09m 0.08m 0.13m',
        backChestPosition: '0m 0.08m -0.13m',
        sleevePosition: '-0.39m -0.05m 0.02m'
    }
};

const clubOptions = {
    ojitos: {
        name: 'Club de los ojitos semi-cerrados',
        image: `${ASSET_PATHS.clubs}CLUB%20-%20OJITOS.png`
    },
    'malas-ideas': {
        name: 'Club de las buenas malas ideas',
        image: `${ASSET_PATHS.clubs}CLUB%20-%20MALAS%20IDEAS.png`
    },
    'asuntos-ajenos': {
        name: 'Club de asuntos ajenos',
        image: `${ASSET_PATHS.clubs}CLUB%20-%20ASUNTOS%20AJENOS.png`
    }
};

const iconOptions = {
    dino: { name: 'Dino', image: `${ASSET_PATHS.icons}DINO.LAT.png` },
    bonie: { name: 'Bonie', image: `${ASSET_PATHS.icons}BONIE-LAT.png` },
    taco: { name: 'Taco', image: `${ASSET_PATHS.icons}TACO-LAT.png` }
};

const state = {
    size: 'M',
    fit: 'regular',
    fitName: 'Regular',
    garmentColor: '#f8f8f6',
    garmentColorName: 'Blanco',
    clubDetailColor: '#ec4d36',
    clubDetailColorName: 'Naranja',
    iconColor: '#ec4d36',
    iconColorName: 'Naranja',
    club: 'ojitos',
    icon: 'dino',
    view: 'front',
    step: 'fit',
    previewMode: '2d',
    customImageUrl: '',
    customImageFile: null
};

const elements = {
    canvas: document.querySelector('#shirt-canvas'),
    stage: document.querySelector('#shirt-stage'),
    stamp: document.querySelector('#shirt-stamp'),
    stampImage: document.querySelector('#stamp-image'),
    backStampImage: document.querySelector('#back-stamp-image'),
    sleeveIcon: document.querySelector('#sleeve-icon'),
    modelViewer: document.querySelector('#shirt-model'),
    modelStamp: document.querySelector('#model-stamp'),
    modelStampImage: document.querySelector('#model-stamp-image'),
    modelBackStamp: document.querySelector('#model-back-stamp'),
    modelBackStampImage: document.querySelector('#model-back-stamp-image'),
    modelSleeveHotspot: document.querySelector('#model-sleeve-hotspot'),
    modelSleeveIcon: document.querySelector('#model-sleeve-icon'),
    sideLabel: document.querySelector('#preview-side-label'),
    previewLabel: document.querySelector('.preview-label'),
    previewNote: document.querySelector('#preview-note'),
    modelError: document.querySelector('#model-error'),
    uploadField: document.querySelector('#upload-field'),
    customImage: document.querySelector('#custom-image'),
    uploadError: document.querySelector('#upload-error'),
    garmentColorName: document.querySelector('#garment-color-name'),
    clubDetailColorName: document.querySelector('#club-detail-color-name'),
    iconColorName: document.querySelector('#icon-color-name'),
    iconColorMatrix: document.querySelector('#icon-color-matrix'),
    summaryDesign: document.querySelector('#summary-design'),
    summaryClub: document.querySelector('#summary-club'),
    form: document.querySelector('#order-form'),
    formError: document.querySelector('#form-error'),
    result: document.querySelector('#whatsapp-result'),
    whatsappLink: document.querySelector('#whatsapp-link')
};

const context = elements.canvas.getContext('2d', { willReadFrequently: true });
let drawRequest = 0;
let modelViewerLoader;
let shirtModelLoader;
let previewRequestId = 0;
let decalReferenceModelPath = '';
let decalReferenceRadius = 0;

function setPressed(buttons, selectedButton) {
    buttons.forEach(button => {
        const selected = button === selectedButton;
        button.classList.toggle('is-selected', selected);
        button.setAttribute('aria-pressed', String(selected));
    });
}

function setStep(stepName) {
    state.step = stepName;
    elements.stage.classList.toggle('is-base-step', stepName === 'fit');

    document.querySelectorAll('.step-tab').forEach(tab => {
        const selected = tab.dataset.step === stepName;
        tab.classList.toggle('is-active', selected);
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
    });

    document.querySelectorAll('.step-panel').forEach(panel => {
        panel.hidden = panel.dataset.panel !== stepName;
    });

    update3DDecalVisibility();
}

function hexToRgb(hex) {
    const value = hex.slice(1);
    return {
        red: Number.parseInt(value.slice(0, 2), 16),
        green: Number.parseInt(value.slice(2, 4), 16),
        blue: Number.parseInt(value.slice(4, 6), 16)
    };
}

function srgbToLinear(channel) {
    const value = channel / 255;
    return value <= 0.04045
        ? value / 12.92
        : ((value + 0.055) / 1.055) ** 2.4;
}

function drawBackSizeLabel() {
    const width = elements.canvas.width;
    const height = elements.canvas.height;
    // Replace the M baked into the back reference while preserving the label's local shading.
    const patchX = Math.round(width * 0.492);
    const patchY = Math.round(height * 0.07);
    const patchWidth = Math.round(width * 0.02);
    const patchHeight = Math.round(height * 0.018);
    const surrounding = context.getImageData(patchX - 2, patchY, patchWidth + 4, patchHeight);
    const patch = context.createImageData(patchWidth, patchHeight);

    for (let y = 0; y < patchHeight; y += 1) {
        const rowStart = y * surrounding.width * 4;
        const left = [0, 1, 2].map(channel => surrounding.data[rowStart + channel]);
        const rightStart = rowStart + (surrounding.width - 1) * 4;
        const right = [0, 1, 2].map(channel => surrounding.data[rightStart + channel]);

        for (let x = 0; x < patchWidth; x += 1) {
            const progress = (x + 1) / (patchWidth + 1);
            const pixelIndex = (y * patchWidth + x) * 4;
            for (let channel = 0; channel < 3; channel += 1) {
                patch.data[pixelIndex + channel] = Math.round(left[channel] * (1 - progress) + right[channel] * progress);
            }
            patch.data[pixelIndex + 3] = 255;
        }
    }

    context.putImageData(patch, patchX, patchY);
    context.save();
    context.fillStyle = '#b0b0b0';
    context.font = `${Math.round(width * 0.016)}px Arial, sans-serif`;
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(state.size, patchX + patchWidth / 2, patchY + patchHeight / 2, patchWidth);
    context.restore();
}

function drawShirt() {
    const request = ++drawRequest;
    const image = new Image();
    const imagePath = state.view === 'back'
        ? `${ASSET_PATHS.shirts}REMERA%20-%20DETRAS.png`
        : fitAssets[state.fit];

    image.addEventListener('load', () => {
        if (request !== drawRequest) {
            return;
        }

        elements.canvas.width = image.naturalWidth;
        elements.canvas.height = image.naturalHeight;
        context.clearRect(0, 0, elements.canvas.width, elements.canvas.height);
        context.drawImage(image, 0, 0);

        if (state.view === 'back') {
            drawBackSizeLabel();
        }

        if (state.garmentColor !== '#f8f8f6') {
            const imageData = context.getImageData(0, 0, elements.canvas.width, elements.canvas.height);
            const pixels = imageData.data;
            const target = hexToRgb(state.garmentColor);

            for (let index = 0; index < pixels.length; index += 4) {
                if (pixels[index + 3] === 0) {
                    continue;
                }

                const luminance = (pixels[index] * 0.299 + pixels[index + 1] * 0.587 + pixels[index + 2] * 0.114) / 255;
                const shade = Math.min(1, Math.max(0.3, luminance));
                pixels[index] = Math.round(target.red * shade);
                pixels[index + 1] = Math.round(target.green * shade);
                pixels[index + 2] = Math.round(target.blue * shade);
            }

            context.putImageData(imageData, 0, 0);
        }

        elements.canvas.setAttribute('aria-label', `Remera ${state.fitName}, talle ${state.size}, color ${state.garmentColorName}, vista de ${state.view === 'front' ? 'frente' : 'espalda'}`);
    });

    image.addEventListener('error', () => {
        if (request !== drawRequest) {
            return;
        }

        elements.formError.hidden = false;
        elements.formError.textContent = 'No se pudo cargar la imagen de la remera. Revisá la carpeta de referencias de las remeras.';
    }, { once: true });

    image.src = imagePath;
}

function updateStamp() {
    if (state.club === 'custom') {
        [elements.stampImage, elements.backStampImage, elements.modelStampImage, elements.modelBackStampImage].forEach(image => {
            if (state.customImageUrl) {
                image.src = state.customImageUrl;
                image.alt = 'Foto personalizada del usuario';
            } else {
                image.removeAttribute('src');
                image.alt = '';
            }
        });
    } else {
        const club = clubOptions[state.club];
        elements.stampImage.src = club.image;
        elements.backStampImage.src = club.image;
        elements.modelStampImage.src = club.image;
        elements.modelBackStampImage.src = club.image;
        elements.stampImage.alt = '';
        elements.backStampImage.alt = '';
        elements.modelStampImage.alt = '';
        elements.modelBackStampImage.alt = '';
    }

    elements.sleeveIcon.src = iconOptions[state.icon].image;
    elements.modelSleeveIcon.src = iconOptions[state.icon].image;
    document.querySelectorAll('.icon-option img').forEach(image => {
        image.style.filter = 'url(#icon-color-filter)';
    });
    updateIconColor();
}

function updateIconColor() {
    const color = hexToRgb(state.iconColor);
    const [red, green, blue] = [color.red, color.green, color.blue].map(channel => channel / 255);
    const luminance = [0.2126, 0.7152, 0.0722];
    const matrix = [red, green, blue]
        .flatMap(channel => [...luminance.map(weight => (channel * weight).toFixed(6)), 0, 0])
        .concat([0, 0, 0, 1, 0]);

    elements.iconColorMatrix.setAttribute('values', matrix.join(' '));
    elements.sleeveIcon.style.filter = 'url(#icon-color-filter)';
    elements.modelSleeveIcon.style.filter = 'url(#icon-color-filter)';
}

function updateModelColor() {
    const materials = elements.modelViewer.model?.materials;
    if (!materials) {
        return;
    }

    const material = materials.find(item => item.name === 'Fabric');

    if (!material) {
        const error = new Error('El modelo 3D no contiene el material “Fabric” esperado.');
        console.error('No se pudo cambiar el color de la remera:', error);
        elements.modelError.textContent = `${error.message} Podés seguir usando la vista 2D.`;
        elements.modelError.hidden = false;
        return;
    }

    const color = hexToRgb(state.garmentColor);
    material.pbrMetallicRoughness.setBaseColorFactor([
        srgbToLinear(color.red),
        srgbToLinear(color.green),
        srgbToLinear(color.blue),
        1
    ]);
}

function update3DDecalVisibility() {
    if (!elements.modelViewer.model) {
        return;
    }

    const facing = Math.cos(elements.modelViewer.getCameraOrbit().theta);
    const showDetails = state.step !== 'fit';
    elements.modelStamp.hidden = !showDetails || facing <= 0.15;
    elements.modelBackStamp.hidden = !showDetails || facing >= -0.15;
    elements.modelSleeveHotspot.hidden = !showDetails;
}

function update3DDecalScale() {
    if (!elements.modelViewer.model) {
        return;
    }

    const modelPath = elements.modelViewer.getAttribute('src');
    const radius = elements.modelViewer.getCameraOrbit().radius;
    if (!Number.isFinite(radius) || radius <= 0) {
        return;
    }

    if (modelPath !== decalReferenceModelPath || decalReferenceRadius <= 0) {
        decalReferenceModelPath = modelPath;
        decalReferenceRadius = radius;
    }

    const scale = decalReferenceRadius / radius;
    elements.modelStamp.style.width = `${52 * scale}px`;
    elements.modelBackStamp.style.width = `${104 * scale}px`;
    elements.modelSleeveHotspot.style.width = `${24 * scale}px`;
}

function updateClubDetailColor() {
    elements.stage.style.setProperty('--club-detail-color', state.clubDetailColor);
}

function loadModelViewer() {
    if (customElements.get('model-viewer')) {
        return Promise.resolve();
    }

    if (!modelViewerLoader) {
        modelViewerLoader = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.type = 'module';
            script.src = 'https://ajax.googleapis.com/ajax/libs/model-viewer/4.0.0/model-viewer.min.js';
            script.addEventListener('load', resolve, { once: true });
            script.addEventListener('error', () => {
                reject(new Error('No se pudo cargar el visor 3D desde Google CDN.'));
            }, { once: true });
            document.head.append(script);
        }).then(() => customElements.whenDefined('model-viewer'));
    }

    return modelViewerLoader;
}

function loadShirtModel(modelPath) {
    if (elements.modelViewer.getAttribute('src') === modelPath && elements.modelViewer.model) {
        return Promise.resolve();
    }

    if (shirtModelLoader?.src === modelPath) {
        return shirtModelLoader.promise;
    }

    shirtModelLoader?.cancel();
    let cleanup;
    let rejectLoad;
    const promise = new Promise((resolve, reject) => {
        rejectLoad = reject;
        const handleLoad = () => {
            if (elements.modelViewer.getAttribute('src') !== modelPath) {
                return;
            }

            cleanup();
            shirtModelLoader = undefined;
            resolve();
        };
        const handleError = () => {
            if (elements.modelViewer.getAttribute('src') !== modelPath) {
                return;
            }

            cleanup();
            shirtModelLoader = undefined;
            elements.modelViewer.removeAttribute('src');
            reject(new Error('No se pudo cargar el modelo 3D de la remera.'));
        };

        cleanup = () => {
            elements.modelViewer.removeEventListener('load', handleLoad);
            elements.modelViewer.removeEventListener('error', handleError);
        };
        elements.modelViewer.addEventListener('load', handleLoad);
        elements.modelViewer.addEventListener('error', handleError);
    });

    shirtModelLoader = {
        src: modelPath,
        promise,
        cancel() {
            cleanup();
            rejectLoad(new Error('Se canceló la carga del modelo 3D anterior.'));
        }
    };
    elements.modelViewer.setAttribute('camera-orbit', '0deg 75deg 105%');
    elements.modelViewer.setAttribute('src', modelPath);
    return promise;
}

function set2DView(view) {
    previewRequestId += 1;
    state.previewMode = '2d';
    state.view = view;
    elements.stage.classList.remove('is-3d', 'is-back');
    elements.stage.classList.toggle('is-back', view === 'back');
    elements.previewLabel.textContent = 'VISTA PREVIA · 2D';
    elements.sideLabel.textContent = view === 'front' ? 'FRENTE' : 'ESPALDA';
    elements.previewNote.textContent = 'El color puede variar levemente entre las vistas 2D y 3D por la iluminación. Arrastrá la remera para explorarla en 360°.';
    elements.modelError.hidden = true;
    setPressed(document.querySelectorAll('.view-button'), document.querySelector(`.view-button[data-view="${view}"]`));
    drawShirt();
}

async function show3DView() {
    const requestId = ++previewRequestId;
    const model = fitModels[state.fit];
    const modelChanged = elements.modelViewer.getAttribute('src') !== model.src;
    elements.modelError.hidden = true;
    elements.stage.classList.add('is-3d');

    try {
        await loadModelViewer();
        await loadShirtModel(model.src);
        if (requestId !== previewRequestId) {
            return;
        }

        if (modelChanged) {
            elements.modelViewer.setAttribute('camera-orbit', '0deg 75deg 105%');
            await new Promise(resolve => {
                window.requestAnimationFrame(() => window.requestAnimationFrame(resolve));
            });
            decalReferenceModelPath = model.src;
            decalReferenceRadius = elements.modelViewer.getCameraOrbit().radius;
        }

        state.previewMode = '3d';
        elements.modelStamp.setAttribute('data-position', model.chestPosition);
        elements.modelBackStamp.setAttribute('data-position', model.backChestPosition);
        elements.modelSleeveHotspot.setAttribute('data-position', model.sleevePosition);
        elements.previewLabel.textContent = 'VISTA 3D · ARRASTRÁ PARA GIRAR';
        elements.modelViewer.setAttribute('alt', `Remera Club House ${state.fitName} personalizada en vista 3D, arrastrá para girarla`);
        elements.previewNote.textContent = 'Arrastrá la remera para girarla. El color puede variar levemente por la iluminación.';
        setPressed(document.querySelectorAll('.view-button'), document.querySelector('.view-button[data-view="3d"]'));
        updateModelColor();
        update3DDecalScale();
    } catch (error) {
        if (requestId !== previewRequestId) {
            return;
        }

        console.error('No se pudo mostrar el modelo 3D:', error);
        elements.stage.classList.remove('is-3d');
        elements.modelError.textContent = `${error.message} Podés seguir usando la vista 2D.`;
        elements.modelError.hidden = false;
        set2DView(state.view);
    }
}

function updateSummary() {
    const clubName = state.club === 'custom'
        ? 'Imagen personalizada'
        : clubOptions[state.club].name;

    elements.summaryDesign.textContent = `Remera ${state.fitName} · talle ${state.size} · ${state.garmentColorName}`;
    elements.summaryClub.textContent = `${clubName} · detalle ${state.clubDetailColorName.toLowerCase()} · ícono de ${iconOptions[state.icon].name} · ${state.iconColorName}`;
    elements.garmentColorName.textContent = `· ${state.garmentColorName}`;
    elements.clubDetailColorName.textContent = `· ${state.clubDetailColorName}`;
    elements.iconColorName.textContent = `· ${state.iconColorName}`;
}

document.querySelectorAll('.step-tab').forEach(tab => {
    tab.addEventListener('click', () => setStep(tab.dataset.step));
});

document.querySelectorAll('.next-step').forEach(button => {
    button.addEventListener('click', () => {
        if (state.club === 'custom' && !state.customImageFile) {
            setStep('club');
            elements.uploadError.hidden = false;
            elements.uploadError.textContent = 'Subí una foto para poder continuar con la opción personalizada.';
            elements.customImage.focus();
            return;
        }

        setStep(button.dataset.next);
        updateSummary();
    });
});

document.querySelectorAll('.previous-step').forEach(button => {
    button.addEventListener('click', () => setStep(button.dataset.previous));
});

document.querySelectorAll('.size-option').forEach(button => {
    button.addEventListener('click', () => {
        state.size = button.dataset.size;
        setPressed(document.querySelectorAll('.size-option'), button);
        drawShirt();
        updateSummary();
    });
});

document.querySelectorAll('.fit-option').forEach(button => {
    button.addEventListener('click', () => {
        state.fit = button.dataset.fit;
        state.fitName = button.querySelector('span').textContent;
        setPressed(document.querySelectorAll('.fit-option'), button);
        set2DView(state.previewMode === '3d' ? 'front' : state.view);
        updateSummary();
    });
});

document.querySelectorAll('#garment-swatches .color-swatch').forEach(button => {
    button.style.setProperty('--swatch-color', button.dataset.color);
    button.addEventListener('click', () => {
        state.garmentColor = button.dataset.color;
        state.garmentColorName = button.dataset.name;
        setPressed(document.querySelectorAll('#garment-swatches .color-swatch'), button);
        elements.garmentColorName.textContent = `· ${state.garmentColorName}`;
        drawShirt();
        updateModelColor();
        updateSummary();
    });
});

document.querySelectorAll('#icon-color-swatches .color-swatch').forEach(button => {
    button.style.setProperty('--swatch-color', button.dataset.color);
    button.addEventListener('click', () => {
        state.iconColor = button.dataset.color;
        state.iconColorName = button.dataset.name;
        setPressed(document.querySelectorAll('#icon-color-swatches .color-swatch'), button);
        updateIconColor();
        updateSummary();
    });
});

document.querySelectorAll('#club-detail-swatches .color-swatch').forEach(button => {
    button.style.setProperty('--swatch-color', button.dataset.color);
    button.addEventListener('click', () => {
        state.clubDetailColor = button.dataset.color;
        state.clubDetailColorName = button.dataset.name;
        setPressed(document.querySelectorAll('#club-detail-swatches .color-swatch'), button);
        updateClubDetailColor();
        updateSummary();
    });
});

document.querySelectorAll('.club-option').forEach(button => {
    button.addEventListener('click', () => {
        state.club = button.dataset.club;
        setPressed(document.querySelectorAll('.club-option'), button);
        elements.uploadField.hidden = state.club !== 'custom';
        elements.uploadError.hidden = true;
        updateStamp();
        updateSummary();
    });
});

document.querySelectorAll('.icon-option').forEach(button => {
    button.addEventListener('click', () => {
        state.icon = button.dataset.icon;
        setPressed(document.querySelectorAll('.icon-option'), button);
        elements.sleeveIcon.src = iconOptions[state.icon].image;
        elements.modelSleeveIcon.src = iconOptions[state.icon].image;
        updateIconColor();
        updateSummary();
    });
});

elements.customImage.addEventListener('change', () => {
    const [file] = elements.customImage.files;
    elements.uploadError.hidden = true;

    if (!file) {
        return;
    }

    if (!file.type.startsWith('image/')) {
        elements.customImage.value = '';
        elements.uploadError.hidden = false;
        elements.uploadError.textContent = 'Elegí un archivo de imagen válido.';
        return;
    }

    if (file.size > MAX_UPLOAD_SIZE) {
        elements.customImage.value = '';
        elements.uploadError.hidden = false;
        elements.uploadError.textContent = 'La imagen supera el límite de 8 MB.';
        return;
    }

    if (state.customImageUrl) {
        URL.revokeObjectURL(state.customImageUrl);
    }

    state.customImageFile = file;
    state.customImageUrl = URL.createObjectURL(file);
    updateStamp();
    updateSummary();
});

document.querySelectorAll('.view-button').forEach(button => {
    button.addEventListener('click', () => {
        if (button.dataset.view === '3d') {
            if (state.previewMode !== '3d') {
                show3DView();
            }
            return;
        }

        if (state.previewMode === '2d' && state.view === button.dataset.view) {
            return;
        }

        set2DView(button.dataset.view);
        elements.stage.classList.add('is-flipping');
        window.setTimeout(() => elements.stage.classList.remove('is-flipping'), 430);
    });
});

elements.modelViewer.addEventListener('load', () => {
    updateModelColor();
    update3DDecalVisibility();
    update3DDecalScale();
});
elements.modelViewer.addEventListener('camera-change', () => {
    update3DDecalVisibility();
    update3DDecalScale();
});

function formatPrice() {
    return new Intl.NumberFormat('es-AR').format(PRICE);
}

function buildOrderMessage(formData) {
    const clubName = state.club === 'custom'
        ? 'Diseño personalizado (foto de referencia)'
        : clubOptions[state.club].name;
    const lines = [
        '¡Hola! Quiero encargar una remera de Club House.',
        '',
        `Modelo: ${state.fitName}`,
        `Talle: ${state.size}`,
        `Color: ${state.garmentColorName}`,
        `Club / diseño: ${clubName}`,
        `Color del detalle del club: ${state.clubDetailColorName}`,
        `Ícono lateral: ${iconOptions[state.icon].name}`,
        `Color del ícono lateral: ${state.iconColorName}`,
        `Precio publicado: $${formatPrice()} ARS`,
        '',
        `Nombre: ${formData.get('customer-name')}`,
        `Mi WhatsApp: ${formData.get('customer-phone')}`,
        `Email: ${formData.get('customer-email') || 'No indicado'}`,
        `Dirección: ${formData.get('customer-address')}`,
        `Ciudad: ${formData.get('customer-city')}`,
        `Provincia: ${formData.get('customer-province')}`,
        `Código postal: ${formData.get('customer-postal')}`,
        `Indicaciones: ${formData.get('customer-notes') || 'Sin indicaciones'}`,
        '',
        'Por favor, confirmen disponibilidad, envío y medios de pago.'
    ];

    if (state.club === 'custom') {
        lines.push('', `Adjuntaré la foto de referencia (${state.customImageFile.name}) directamente en este chat.`);
    }

    return lines.join('\n');
}

elements.form.addEventListener('submit', event => {
    event.preventDefault();
    elements.formError.hidden = true;
    elements.result.hidden = true;

    if (!elements.form.reportValidity()) {
        return;
    }

    if (state.club === 'custom' && !state.customImageFile) {
        setStep('club');
        elements.uploadError.hidden = false;
        elements.uploadError.textContent = 'Subí una foto para poder enviar el pedido personalizado.';
        elements.customImage.focus();
        return;
    }

    const whatsappNumber = window.SHOP_CONFIG?.whatsappNumber?.replace(/\D/g, '');
    if (!whatsappNumber) {
        elements.formError.hidden = false;
        elements.formError.textContent = 'Falta configurar el WhatsApp de la tienda en js/shop-config.local.js.';
        return;
    }

    const message = buildOrderMessage(new FormData(elements.form));
    elements.whatsappLink.href = `https://wa.me/${whatsappNumber}?text=${encodeURIComponent(message)}`;
    elements.result.hidden = false;
    elements.result.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
});

document.querySelectorAll('.view-button').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.view === state.view));
});
document.querySelectorAll('.color-swatch').forEach(button => {
    button.style.setProperty('--swatch-color', button.dataset.color);
});
setStep('fit');
drawShirt();
updateClubDetailColor();
updateStamp();
updateSummary();
