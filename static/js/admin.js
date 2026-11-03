// Admin CMS behaviour: Markdown editor, Cloudinary direct uploads,
// slug preview, unsaved-changes guard.
(function () {
  "use strict";

  var MAX_BYTES = 10 * 1024 * 1024; // Cloudinary free-plan image limit

  // ---------- Unsaved-changes guard ----------
  var dirty = false;
  function markDirty() { dirty = true; }
  document.querySelectorAll("form[data-dirty-guard]").forEach(function (form) {
    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);
    form.addEventListener("submit", function () { dirty = false; });
  });
  window.addEventListener("beforeunload", function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ""; }
  });

  // ---------- Markdown editor ----------
  if (window.EasyMDE) {
    document.querySelectorAll("textarea[data-markdown]").forEach(function (el) {
      var mde = new EasyMDE({
        element: el,
        forceSync: true,
        spellChecker: false,
        status: ["lines", "words"],
        minHeight: el.rows > 12 ? "420px" : "220px",
        renderingConfig: { codeSyntaxHighlighting: false },
        toolbar: ["bold", "italic", "heading", "|", "quote", "code", "unordered-list", "ordered-list", "|",
                  "link", "image", "table", "|", "preview", "side-by-side", "fullscreen", "|", "guide"],
      });
      mde.codemirror.on("change", markDirty);
      // HTML5 `required` can't validate a hidden textarea; EasyMDE hides it.
      el.removeAttribute("required");
    });
  }

  // ---------- Slug preview ----------
  var slugSrc = document.querySelector("[data-slug-source]");
  var slugDst = document.querySelector("[data-slug-target]");
  if (slugSrc && slugDst) {
    var manual = slugDst.value !== "";
    slugDst.addEventListener("input", function () { manual = slugDst.value !== ""; });
    slugSrc.addEventListener("input", function () {
      if (manual) return;
      slugDst.placeholder = slugSrc.value.toLowerCase().normalize("NFKD")
        .replace(/[̀-ͯ]/g, "").replace(/[^\w\s-]/g, "").trim().replace(/[\s_-]+/g, "-").slice(0, 80);
    });
  }

  // ---------- Cloudinary direct upload ----------
  async function getSignature(kind) {
    var res = await fetch("/admin/api/upload-signature", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: kind }),
    });
    if (res.status === 401) { window.location.href = "/admin/login"; throw new Error("Session expired"); }
    if (!res.ok) {
      var detail = "";
      try { detail = (await res.json()).detail || ""; } catch (e) { /* non-JSON error page */ }
      throw new Error("Could not get upload signature (HTTP " + res.status + ")" + (detail ? ": " + detail : ""));
    }
    return res.json();
  }

  async function uploadFile(file, kind) {
    if (!file.type.startsWith("image/")) throw new Error(file.name + " is not an image");
    if (file.size > MAX_BYTES) throw new Error(file.name + " is larger than 10 MB");
    var sig = await getSignature(kind);
    var fd = new FormData();
    fd.append("file", file);
    ["api_key", "timestamp", "signature", "folder", "transformation"].forEach(function (k) { fd.append(k, sig[k]); });
    var res = await fetch("https://api.cloudinary.com/v1_1/" + encodeURIComponent(sig.cloud_name) + "/image/upload", {
      method: "POST",
      body: fd,
    });
    var data = await res.json();
    if (!res.ok) throw new Error((data.error && data.error.message) || "Upload failed");
    return {
      publicId: data.public_id,
      preview: "https://res.cloudinary.com/" + sig.cloud_name + "/image/upload/c_fill,w_320,h_224,g_auto,f_auto,q_auto/" + data.public_id,
    };
  }

  function makeItem(name, publicId, previewUrl) {
    var fig = document.createElement("figure");
    fig.setAttribute("data-item", "");
    fig.className = "group relative h-28 w-40 overflow-hidden rounded-lg border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800";
    var img = document.createElement("img");
    img.src = previewUrl; img.alt = ""; img.className = "h-full w-full object-cover";
    var input = document.createElement("input");
    input.type = "hidden"; input.name = name; input.value = publicId;
    var btn = document.createElement("button");
    btn.type = "button"; btn.setAttribute("data-remove", ""); btn.setAttribute("aria-label", "Remove image");
    btn.className = "absolute right-1 top-1 rounded-full bg-black/70 px-2 text-sm text-white opacity-90 hover:bg-red-600";
    btn.textContent = "×";
    fig.append(img, input, btn);
    return fig;
  }

  document.querySelectorAll("[data-uploader]").forEach(function (root) {
    var name = root.dataset.name;
    var kind = root.dataset.kind;
    var multiple = root.dataset.multiple === "true";
    var previews = root.querySelector("[data-previews]");
    var fileInput = root.querySelector("input[type=file]");
    var status = root.querySelector("[data-status]");

    // Removing must still submit an empty value for single-image fields,
    // otherwise the server would keep the old image.
    function ensureEmptyField() {
      if (!multiple && !previews.querySelector("[data-item]") && !root.querySelector("input[data-empty]")) {
        var empty = document.createElement("input");
        empty.type = "hidden"; empty.name = name; empty.value = ""; empty.setAttribute("data-empty", "");
        root.appendChild(empty);
      }
    }

    previews.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-remove]");
      if (!btn) return;
      btn.closest("[data-item]").remove();
      ensureEmptyField();
      markDirty();
    });

    fileInput.addEventListener("change", async function () {
      var files = Array.from(fileInput.files || []);
      if (!files.length) return;
      if (!multiple) files = files.slice(0, 1);
      fileInput.disabled = true;
      var done = 0;
      for (var i = 0; i < files.length; i++) {
        status.textContent = "Uploading " + (i + 1) + " of " + files.length + "…";
        try {
          var r = await uploadFile(files[i], kind);
          if (!multiple) previews.innerHTML = "";
          var stale = root.querySelector("input[data-empty]");
          if (stale) stale.remove();
          previews.appendChild(makeItem(name, r.publicId, r.preview));
          done++;
          markDirty();
        } catch (err) {
          status.textContent = err.message;
          status.className = "text-xs text-red-600";
        }
      }
      if (done === files.length) {
        status.textContent = done + " uploaded. Remember to save.";
        status.className = "text-xs text-emerald-600";
      }
      fileInput.value = "";
      fileInput.disabled = false;
    });

    ensureEmptyField();
  });
})();
