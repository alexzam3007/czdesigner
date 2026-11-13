import hero from '../components/hero/hero.js';
import about from '../components/about/about.js';
import projects from '../components/projects/projects.js';
import contact from '../components/contact/contact.js';

const components = [hero, about, projects, contact];

async function loadComponent(component) {
    const host = document.querySelector(`[data-component="${component.name}"]`);

    if (!host) {
        throw new Error(`No se encontró el espacio para el componente "${component.name}".`);
    }

    const [response] = await Promise.all([
        fetch(component.template),
        loadStylesheet(component.stylesheet)
    ]);

    if (!response.ok) {
        throw new Error(`No se pudo cargar ${component.template.href}: ${response.status}`);
    }

    const template = document.createElement('template');
    template.innerHTML = await response.text();

    if (template.content.children.length !== 1) {
        throw new Error(`${component.template.href} debe contener un único elemento raíz.`);
    }

    const root = template.content.firstElementChild;
    host.replaceWith(template.content);
    await component.mount(root);
}

function loadStylesheet(url) {
    return new Promise((resolve, reject) => {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = url.href;
        link.addEventListener('load', resolve, { once: true });
        link.addEventListener('error', () => {
            reject(new Error(`No se pudo cargar la hoja de estilos ${url.href}.`));
        }, { once: true });
        document.head.append(link);
    });
}

function setupNavbar() {
    const burger = document.querySelector('.burger');
    const nav = document.querySelector('.nav-links');
    const header = document.querySelector('header');

    if (burger && nav) {
        burger.addEventListener('click', () => {
            const isExpanded = burger.getAttribute('aria-expanded') === 'true';
            burger.setAttribute('aria-expanded', String(!isExpanded));
            burger.setAttribute('aria-label', isExpanded ? 'Abrir menú' : 'Cerrar menú');
            nav.classList.toggle('nav-active', !isExpanded);
            burger.classList.toggle('toggle', !isExpanded);
        });

        nav.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                nav.classList.remove('nav-active');
                burger.classList.remove('toggle');
                burger.setAttribute('aria-expanded', 'false');
                burger.setAttribute('aria-label', 'Abrir menú');
            });
        });

        setupActiveSectionLink(nav);
    }

    if (header) {
        const updateHeader = () => {
            header.classList.toggle('scrolled', window.scrollY > 50);
        };

        updateHeader();
        window.addEventListener('scroll', updateHeader, { passive: true });
    }
}

function setupActiveSectionLink(nav) {
    const links = Array.from(nav.querySelectorAll('a[href^="#"]'));
    const sections = links
        .map(link => document.querySelector(link.getAttribute('href')))
        .filter(section => section instanceof HTMLElement);

    if (sections.length === 0) {
        return;
    }

    const updateActiveLink = () => {
        const activeLine = window.innerHeight * 0.4;
        let currentSection = sections[0];

        sections.forEach(section => {
            if (section.getBoundingClientRect().top <= activeLine) {
                currentSection = section;
            }
        });

        links.forEach(link => {
            if (link.hash === `#${currentSection.id}`) {
                link.setAttribute('aria-current', 'location');
            } else {
                link.removeAttribute('aria-current');
            }
        });
    };

    updateActiveLink();
    window.addEventListener('scroll', updateActiveLink, { passive: true });
    window.addEventListener('resize', updateActiveLink);
}

async function initApp() {
    await Promise.all(components.map(loadComponent));
    setupNavbar();
}

initApp().catch(error => {
    console.error('No se pudo iniciar el portafolio:', error);
    const message = document.createElement('p');
    message.className = 'app-error';
    message.setAttribute('role', 'alert');
    message.textContent = 'No se pudo cargar el portafolio. Recarga la página e inténtalo de nuevo.';
    document.querySelector('#main-content')?.prepend(message);
});
