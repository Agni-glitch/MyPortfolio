// Public-site behaviour: theme toggle, mobile menu, form double-submit guard.
(function () {
  "use strict";

  function setTheme(dark) {
    document.documentElement.classList.toggle("dark", dark);
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch (e) {}
  }

  document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setTheme(!document.documentElement.classList.contains("dark"));
    });
  });

  // Follow OS changes only while the user hasn't picked a theme explicitly.
  var mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener && mq.addEventListener("change", function (e) {
    var stored = null;
    try { stored = localStorage.getItem("theme"); } catch (err) {}
    if (!stored) document.documentElement.classList.toggle("dark", e.matches);
  });

  var menuBtn = document.querySelector("[data-menu-toggle]");
  var menu = document.getElementById("mobile-menu");
  if (menuBtn && menu) {
    menuBtn.addEventListener("click", function () {
      var open = menu.classList.toggle("hidden") === false;
      menuBtn.setAttribute("aria-expanded", String(open));
    });
  }

  document.querySelectorAll("form[data-submit-once]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var btn = form.querySelector("button:not([type=button])");
      if (btn) { btn.disabled = true; btn.dataset.label = btn.textContent; btn.textContent = "Please wait…"; }
    });
  });

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });
})();
