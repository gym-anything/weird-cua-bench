(() => {
  "use strict";
  window.WeirdCaptchaMechanics = window.WeirdCaptchaMechanics || {};
  window.WeirdCaptchaMechanics.hologram_silhouette_foundry = {
    rootSelector: ".ivv-hologram-silhouette-foundry",
    render: (state, helpers) => window.WeirdInteractionViiViii.render("hologram_silhouette_foundry", state, helpers),
  };
})();
