(function () {
  "use strict";

  const BUDGET_DEFAULTS = { min: 500, max: 15000, step: 250 };

  function $(sel, el = document) {
    return el.querySelector(sel);
  }
  function $$(sel, el = document) {
    return Array.from(el.querySelectorAll(sel));
  }

  function showView(viewId) {
    $$(".view").forEach((v) => v.classList.remove("active"));
    $$(".nav-btn").forEach((b) => b.classList.remove("active"));
    const view = $("#" + viewId + "-view");
    const btn = $(`.nav-btn[data-view="${viewId}"]`);
    if (view) view.classList.add("active");
    if (btn) btn.classList.add("active");
  }

  function formatBudget(val) {
    return "$" + Number(val).toLocaleString();
  }

  function initBudgetSlider() {
    const slider = $("#budget");
    const output = $("#budget-value");
    if (!slider || !output) return;
    function update() {
      output.textContent = formatBudget(slider.value);
    }
    slider.addEventListener("input", update);
    update();
  }

  function loadAirports() {
    fetch("/api/airports")
      .then((r) => r.json())
      .then((list) => {
        const sel = $("#home-airport");
        if (!sel) return;
        list.forEach(({ code, name }) => {
          const opt = document.createElement("option");
          opt.value = code;
          opt.textContent = name;
          sel.appendChild(opt);
        });
      })
      .catch(console.error);
  }

  function loadDestinations() {
    fetch("/api/destinations")
      .then((r) => r.json())
      .then((list) => {
        const sel = $("#destination");
        if (!sel) return;
        list.forEach((name) => {
          const opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name;
          sel.appendChild(opt);
        });
      })
      .catch(console.error);
  }

  function todayYYYYMMDD() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function isDateBeforeToday(dateStr) {
    if (!dateStr) return false;
    return dateStr < todayYYYYMMDD();
  }

  function isDepartureBeforeReturn(dep, ret) {
    if (!dep || !ret) return true;
    return new Date(dep) < new Date(ret);
  }

  function showDateError(msg) {
    const el = $("#date-error");
    if (el) {
      el.textContent = msg || "";
      el.classList.toggle("visible", !!msg);
    }
  }

  function validateDates() {
    const form = $("#trip-form");
    if (!form) return true;
    const dep = form.departure_date?.value;
    const ret = form.return_date?.value;
    if (!dep || !ret) {
      showDateError("");
      return true;
    }
    if (isDateBeforeToday(dep) || isDateBeforeToday(ret)) {
      showDateError("Departure and return dates must be today or in the future.");
      return false;
    }
    if (!isDepartureBeforeReturn(dep, ret)) {
      showDateError("Return date must be after departure date.");
      return false;
    }
    showDateError("");
    return true;
  }

  function getFormPayload() {
    const form = $("#trip-form");
    if (!form) return null;
    const activityTypes = $$('input[name="activity_types"]:checked', form).map(
      (el) => el.value
    );
    return {
      home_airport: form.home_airport?.value || "",
      departure_date: form.departure_date?.value || "",
      destination: form.destination?.value || "",
      return_date: form.return_date?.value || "",
      budget: Number(form.budget?.value || 0),
      activity_types: activityTypes,
      prefer_red_eyes: !!form.prefer_red_eyes?.checked,
    };
  }

  function setOutput(text) {
    const box = $("#output-box");
    if (box) box.value = text || "";
  }

  function setOutputLoading() {
    setOutput("Generating your plan…");
  }

  function setOutputError(msg) {
    setOutput("Error: " + (msg || "Something went wrong."));
  }

  function submitTrip(e) {
    e.preventDefault();
    if (!validateDates()) return;
    const payload = getFormPayload();
    if (!payload) return;
    setOutputLoading();
    fetch("/api/trip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (ok && data.success && data.output != null) {
          showDateError("");
          setOutput(data.output);
        } else {
          if (data.message && data.message.includes("departure")) showDateError(data.message);
          setOutputError(data.message || "No output returned.");
        }
      })
      .catch((err) => setOutputError(err.message));
  }

  function initNavigation() {
    $$(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const view = btn.getAttribute("data-view");
        if (view) showView(view);
      });
    });
    $$("[data-goto]").forEach((el) => {
      el.addEventListener("click", () => {
        const view = el.getAttribute("data-goto");
        if (view) showView(view);
      });
    });
  }

  function initForm() {
    const form = $("#trip-form");
    if (form) {
      form.addEventListener("submit", submitTrip);
      ["departure_date", "return_date"].forEach((name) => {
        const input = form[name];
        if (input) input.addEventListener("change", validateDates);
      });
      form.addEventListener("reset", () => {
        setTimeout(() => {
          $("#budget-value").textContent = formatBudget(
            $("#budget").value || BUDGET_DEFAULTS.max / 2
          );
          showDateError("");
          setOutput("");
        }, 0);
      });
    }
  }

  function init() {
    initNavigation();
    initBudgetSlider();
    initForm();
    loadAirports();
    loadDestinations();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
