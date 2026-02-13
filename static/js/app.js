(function () {
  "use strict";

  const BUDGET_DEFAULTS = { min: 500, max: 15000, step: 250 };
  let currentPlan = null;

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

  function setResultsState(state) {
    const container = $("#trip-results");
    const placeholder = $("#results-placeholder");
    const content = $("#results-content");
    const errEl = $("#results-error");
    if (!container) return;
    container.setAttribute("data-state", state);
    if (placeholder) placeholder.hidden = state === "plan" || state === "error";
    if (content) content.hidden = state !== "plan";
    if (errEl) {
      errEl.hidden = state !== "error";
      if (state !== "error") errEl.textContent = "";
    }
  }

  function showResultsLoading() {
    setResultsState("loading");
    const placeholder = $("#results-placeholder");
    if (placeholder) placeholder.textContent = "Generating your plan…";
  }

  function showResultsError(msg) {
    setResultsState("error");
    const errEl = $("#results-error");
    if (errEl) errEl.textContent = msg || "Something went wrong.";
  }

  function clearResults() {
    currentPlan = null;
    setResultsState("empty");
    const placeholder = $("#results-placeholder");
    if (placeholder) placeholder.textContent = "Submit the form to see your plan here.";
  }

  function refreshSavedList() {
    fetch("/api/itineraries")
      .then((r) => r.json())
      .then((data) => {
        const list = $("#saved-itineraries-list");
        const emptyMsg = $("#saved-empty-msg");
        if (!list) return;
        list.innerHTML = "";
        const names = data.names || [];
        if (emptyMsg) emptyMsg.hidden = names.length > 0;
        names.forEach((name) => {
          const li = document.createElement("li");
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "saved-itinerary-btn";
          btn.textContent = name;
          btn.addEventListener("click", () => loadSavedItinerary(name));
          li.appendChild(btn);
          list.appendChild(li);
        });
      })
      .catch(console.error);
  }

  function loadSavedItinerary(name) {
    const encoded = encodeURIComponent(name);
    fetch(`/api/itineraries/${encoded}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.success && data.plan) {
          showView("trip");
          renderPlan(data.plan);
          closeSavedPanel();
        }
      })
      .catch(console.error);
  }

  function saveItinerary() {
    const nameInput = $("#itinerary-name");
    const name = (nameInput && nameInput.value || "").trim();
    const msgEl = $("#save-itinerary-msg");
    if (!name) {
      if (msgEl) msgEl.textContent = "Enter a name for this itinerary.";
      return;
    }
    if (!currentPlan) {
      if (msgEl) msgEl.textContent = "No plan to save. Generate a plan first.";
      return;
    }
    if (msgEl) msgEl.textContent = "";
    fetch("/api/itineraries/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name, plan: currentPlan }),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (ok && data.success) {
          if (msgEl) msgEl.textContent = "Saved as \"" + name + "\".";
          if (nameInput) nameInput.value = "";
          refreshSavedList();
        } else {
          if (msgEl) msgEl.textContent = data.message || "Could not save.";
        }
      })
      .catch((err) => {
        if (msgEl) msgEl.textContent = "Error saving.";
      });
  }

  function openSavedPanel() {
    const panel = $("#saved-panel");
    const toggle = $("#toggle-saved-panel");
    if (panel) {
      panel.hidden = false;
      document.body.classList.add("side-panel-open");
      refreshSavedList();
    }
    if (toggle) toggle.setAttribute("aria-expanded", "true");
  }

  function closeSavedPanel() {
    const panel = $("#saved-panel");
    const toggle = $("#toggle-saved-panel");
    if (panel) panel.hidden = true;
    document.body.classList.remove("side-panel-open");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
  }

  function toggleSavedPanel() {
    const panel = $("#saved-panel");
    if (panel && panel.hidden) openSavedPanel();
    else closeSavedPanel();
  }

  function renderPlan(plan) {
    if (!plan) return;
    currentPlan = plan;
    setResultsState("plan");
    const totalEl = $("#result-total-budget");
    const flightsEl = $("#result-flights");
    const daysEl = $("#result-days");
    if (totalEl) totalEl.innerHTML = `<span class="result-total-label">Total budget</span><span class="result-total-amount">${formatBudget(plan.total_budget)}</span>`;
    if (flightsEl) {
      flightsEl.innerHTML = "";
      const heading = document.createElement("h4");
      heading.className = "result-block-title";
      heading.textContent = "Flights";
      flightsEl.appendChild(heading);
      (plan.flights || []).forEach((f) => {
        const box = document.createElement("div");
        box.className = "result-flight-box";
        box.innerHTML = `<div class="result-flight-info">${escapeHtml(f.description || "Flight")}</div><div class="result-flight-cost">${formatBudget(f.cost != null ? f.cost : 0)}</div>`;
        flightsEl.appendChild(box);
      });
    }
    if (daysEl) {
      daysEl.innerHTML = "";
      const heading = document.createElement("h4");
      heading.className = "result-block-title";
      heading.textContent = "Daily itinerary";
      daysEl.appendChild(heading);
      (plan.days || []).forEach((day) => {
        const dayWrap = document.createElement("div");
        dayWrap.className = "result-day-row";
        const dayBox = document.createElement("div");
        dayBox.className = "result-day-box";
        const activitiesList = (day.activities || []).map((a) => `<li>${escapeHtml(a)}</li>`).join("");
        // day.hotel is a string with the hotel info, etc. for each day
        // day.other is a string with the flight info and any other info
        // probably want to grab the other fields from day activities to format out times and things?
        dayBox.innerHTML = `
          <div class="result-day-header">Day ${day.day_number} — ${escapeHtml(day.date || "")}</div>
          <div class="result-day-hotel"><strong>Hotel:</strong> ${escapeHtml(day.hotel || "—")}</div>
          <div class="result-day-activities"><strong>Activities:</strong><ul>${activitiesList || "<li>—</li>"}</ul></div>
          ${day.other ? `<div class="result-day-other">${escapeHtml(day.other)}</div>` : ""}
        `;
        const budgetBox = document.createElement("div");
        budgetBox.className = "result-day-budget";
        budgetBox.innerHTML = `<span class="result-day-budget-label">Daily budget</span><span class="result-day-budget-amount">${formatBudget(day.daily_budget != null ? day.daily_budget : 0)}</span>`;
        dayWrap.appendChild(dayBox);
        dayWrap.appendChild(budgetBox);
        daysEl.appendChild(dayWrap);
      });
    }
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function submitTrip(e) {
    e.preventDefault();
    if (!validateDates()) return;
    const payload = getFormPayload();
    if (!payload) return;
    showResultsLoading();
    fetch("/api/trip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (ok && data.success && data.plan) {
          showDateError("");
          renderPlan(data.plan);
        } else {
          if (data.message && data.message.includes("departure")) showDateError(data.message);
          showResultsError(data.message || "No output returned.");
        }
      })
      .catch((err) => showResultsError(err.message));
  }

  function initNavigation() {
    $$(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const view = btn.getAttribute("data-view");
        if (view) {
          showView(view);
          if (view === "trip") {
            setTimeout(() => {
              const form = $("#trip-form");
              if (form) form.reset();
              $("#budget-value").textContent = formatBudget($("#budget").value || BUDGET_DEFAULTS.max / 2);
              showDateError("");
              clearResults();
            }, 0);
          }
        }
      });
    });
    $$("[data-goto]").forEach((el) => {
      el.addEventListener("click", () => {
        const view = el.getAttribute("data-goto");
        if (view) showView(view);
      });
    });
    const toggleSaved = $("#toggle-saved-panel");
    if (toggleSaved) toggleSaved.addEventListener("click", toggleSavedPanel);
    const closeSaved = $("#close-saved-panel");
    if (closeSaved) closeSaved.addEventListener("click", closeSavedPanel);
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
          clearResults();
        }, 0);
      });
    }
    const saveBtn = $("#save-itinerary-btn");
    if (saveBtn) saveBtn.addEventListener("click", saveItinerary);
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
