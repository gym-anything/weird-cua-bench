(() => {
  "use strict";
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.marionette_checkpoint = {
    rootSelector: ".ivv-marionette-checkpoint",
    render: (state, helpers) => window.WeirdInteractionViiViii.render("marionette_checkpoint", state, helpers),
  };
})();
