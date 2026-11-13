import { observeReveals } from '../../js/components/reveal.js';

export default {
    name: 'projects',
    template: new URL('./projects.html', import.meta.url),
    stylesheet: new URL('./projects.css', import.meta.url),
    mount(root) {
        observeReveals(root, '.work-item');
    }
};
