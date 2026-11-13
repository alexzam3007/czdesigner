import { observeReveals } from '../../js/components/reveal.js';

export default {
    name: 'contact',
    template: new URL('./contact.html', import.meta.url),
    stylesheet: new URL('./contact.css', import.meta.url),
    mount(root) {
        observeReveals(root, '.contact-container');
    }
};
