import { observeReveals } from '../../js/components/reveal.js';

export default {
    name: 'about',
    template: new URL('./about.html', import.meta.url),
    stylesheet: new URL('./about.css', import.meta.url),
    mount(root) {
        observeReveals(root, '.about-intro, .experience-item');
    }
};
