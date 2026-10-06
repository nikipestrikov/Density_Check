/* Allora header behaviour: mobile menu toggle, and the transparent-to-frosted switch on scroll
   for headers with the ac-header--overlay class. No dependencies; safe to load with `defer`. */
(function () {
  'use strict';
  document.querySelectorAll('.ac-header').forEach(function (header) {
    var burger = header.querySelector('.ac-burger');
    var nav = header.querySelector('.ac-nav');
    if (burger && nav) {
      burger.addEventListener('click', function () {
        var open = nav.classList.toggle('is-open');
        burger.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    }
    if (header.classList.contains('ac-header--overlay')) {
      var update = function () { header.classList.toggle('is-scrolled', window.scrollY > 40); };
      update();
      window.addEventListener('scroll', update, { passive: true });
    }
  });
})();
