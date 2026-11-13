import { observeReveals } from '../../js/components/reveal.js';

export default {
    name: 'hero',
    template: new URL('./hero.html', import.meta.url),
    stylesheet: new URL('./hero.css', import.meta.url),
    mount(root) {
        setupTypewriter(root);
        observeReveals(root, '.main-title');
        setupParallax(root);
    }
};

function setupTypewriter(root) {
    const heading = root.querySelector('.main-title');
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    if (prefersReducedMotion.matches) {
        return;
    }

    const lines = Array.from(heading.querySelectorAll('span'));
    const phrases = lines.map(line => Array.from(line.textContent.trim()));
    const typeDelay = 180;
    const eraseDelay = 80;
    let isRunning = true;

    lines.forEach(line => {
        line.textContent = '';
    });

    const showFullText = () => {
        isRunning = false;
        lines.forEach((line, index) => {
            line.textContent = phrases[index].join('');
            line.classList.remove('is-typing');
        });
    };

    const handleMotionPreferenceChange = event => {
        if (event.matches) {
            showFullText();
            prefersReducedMotion.removeEventListener('change', handleMotionPreferenceChange);
        }
    };

    prefersReducedMotion.addEventListener('change', handleMotionPreferenceChange);

    const pause = delay => new Promise(resolve => window.setTimeout(resolve, delay));

    async function animateText() {
        while (isRunning) {
            for (let index = 0; index < lines.length; index += 1) {
                if (!isRunning) return;

                const line = lines[index];
                line.classList.add('is-typing');

                for (const character of phrases[index]) {
                    if (!isRunning) return;
                    line.textContent += character;
                    await pause(typeDelay);
                }

                line.classList.remove('is-typing');
                await pause(120);
            }

            await pause(1200);

            for (let index = lines.length - 1; index >= 0; index -= 1) {
                if (!isRunning) return;

                const line = lines[index];
                const characters = Array.from(line.textContent);
                line.classList.add('is-typing');

                while (characters.length > 0) {
                    if (!isRunning) return;
                    characters.pop();
                    line.textContent = characters.join('');
                    await pause(eraseDelay);
                }

                line.classList.remove('is-typing');
                await pause(120);
            }

            await pause(400);
        }
    }

    animateText();
}

function setupParallax(root) {
    const heroImage = root.querySelector('.hero-background-image');

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        return;
    }

    window.addEventListener('scroll', () => {
        heroImage.style.transform = `translateY(${window.scrollY * 0.1}px)`;
    }, { passive: true });
}
