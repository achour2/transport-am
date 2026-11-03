/* Talaouglid — petites interactions pour un site plus fluide (sans dépendance) */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");
  var reduit = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Barre de navigation : se resserre quand on défile
  var nav = document.querySelector(".navbar-tb");
  function majNav() { if (nav) nav.classList.toggle("defile", window.scrollY > 12); }
  window.addEventListener("scroll", majNav, { passive: true });
  majNav();

  // Lien actif dans le menu
  var chemin = location.pathname;
  document.querySelectorAll(".navbar-tb .navbar-nav a.nav-link[href]").forEach(function (a) {
    var href = a.getAttribute("href");
    if (href && href !== "#" && href !== "/" && chemin.indexOf(href) === 0) {
      a.classList.add("active");
      a.setAttribute("aria-current", "page");
    }
  });

  // Messages : disparaissent seuls après quelques secondes (sauf les erreurs)
  document.querySelectorAll(".zone-messages .alert").forEach(function (al, i) {
    if (al.classList.contains("alert-danger")) return;
    setTimeout(function () {
      al.classList.add("sortie");
      setTimeout(function () { al.remove(); }, 320);
    }, 5000 + i * 600);
  });

  // Apparition douce des blocs marqués .reveal
  var blocs = document.querySelectorAll(".reveal");
  if (!reduit && "IntersectionObserver" in window) {
    var obs = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("visible"); obs.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    blocs.forEach(function (b) { obs.observe(b); });
  } else {
    blocs.forEach(function (b) { b.classList.add("visible"); });
  }

  // Bouton d'envoi : petit indicateur de chargement, et pas de double clic
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (e.defaultPrevented || (form.method || "").toLowerCase() !== "post" || form.hasAttribute("data-sans-chargement")) return;
    var btn = e.submitter || form.querySelector("button[type=submit], button:not([type])");
    if (!btn || btn.classList.contains("dropdown-item")) return;
    setTimeout(function () {  // après la construction des données du formulaire
      btn.disabled = true;
      btn.dataset.texte = btn.innerHTML;
      btn.innerHTML = '<span class="spinner-border" role="status" aria-hidden="true"></span> ' + btn.textContent.trim();
    }, 0);
  });
  // Retour arrière du navigateur : réactiver les boutons
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    document.querySelectorAll("button[data-texte]").forEach(function (b) { b.disabled = false; b.innerHTML = b.dataset.texte; });
  });

  // Compteurs animés (data-compteur="123")
  document.querySelectorAll("[data-compteur]").forEach(function (el) {
    var cible = parseFloat(el.getAttribute("data-compteur")) || 0;
    if (reduit || cible <= 0) { el.textContent = cible; return; }
    var debut = null;
    function pas(t) {
      if (!debut) debut = t;
      var p = Math.min((t - debut) / 900, 1);
      el.textContent = Math.round(cible * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(pas);
    }
    requestAnimationFrame(pas);
  });
})();
