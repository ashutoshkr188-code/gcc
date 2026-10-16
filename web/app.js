"use strict";
// GCC Atlas front end. Every value shown comes from the /api endpoints (SQLite).

const $ = (sel, el = document) => el.querySelector(sel);
const main = () => $("#main");

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function safeUrl(u) {
  try { const x = new URL(u); return ["http:", "https:"].includes(x.protocol) ? x.href : "#"; } catch { return "#"; }
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}
const qs = o => new URLSearchParams(Object.entries(o).flatMap(([k, v]) =>
  v == null || v === "" ? [] : Array.isArray(v) ? v.map(x => [k, x]) : [[k, v]])).toString();

// ---------- shared UI pieces ----------

const STATUS_CLASS = {
  verified_official: "ok", verified_independent: "ok", needs_review: "info", extracted: "info",
  conflicting: "bad", rejected: "bad", possibly_outdated: "warn", unverified: "warn", discovered: "",
};
const STATUS_HELP = {
  discovered: "Found through web search. The source has not been read yet.",
  extracted: "Text was extracted from the source but not yet checked.",
  verified_official: "Checked against the text of an official source.",
  verified_independent: "Checked against two or more independent publications.",
  needs_review: "Supporting text was found automatically and is waiting for a person to confirm it.",
  conflicting: "Sources disagree.",
  possibly_outdated: "The source may no longer be current.",
  unverified: "The source was read but did not support this.",
  rejected: "Reviewed and found to be wrong.",
};
function statusBadge(status, label) {
  return `<span class="badge ${STATUS_CLASS[status] || ""}" title="${esc(STATUS_HELP[status] || "")}">${esc(label || status)}</span>`;
}
const OP_LABEL = { operating: "Operating", announced: "Announced", general_office: "General office", unverified_lead: "Unverified lead", closed: "Closed" };
function opBadge(s) { return `<span class="badge ${s === "operating" ? "ok" : s === "unverified_lead" ? "warn" : ""}">${esc(OP_LABEL[s] || s)}</span>`; }
const RET_LABEL = { retrieved: "Retrieved", network_blocked: "Blocked by network", http_error: "HTTP error", failed: "Failed", not_attempted: "Not attempted" };
function retBadge(s) { return `<span class="badge ${s === "retrieved" ? "ok" : s === "not_attempted" ? "" : "bad"}">${esc(RET_LABEL[s] || s)}</span>`; }

// Every important number explains what it means, where it came from, the period it covers and how it was checked.
function stat(value, label, ex) {
  return `<div class="card stat"><div class="value">${esc(value)}</div><div class="label">${esc(label)}</div>
    <details class="explain"><summary>What does this mean?</summary><dl>
      <dt>Meaning</dt><dd>${esc(ex.meaning)}</dd>
      <dt>Where it comes from</dt><dd>${esc(ex.source)}</dd>
      <dt>Period</dt><dd>${esc(ex.period)}</dd>
      <dt>How it was checked</dt><dd>${esc(ex.check)}</dd></dl></details></div>`;
}
function empty(msg) { return `<div class="empty">${msg}</div>`; }
function loading() { main().innerHTML = `<p class="muted">Loading…</p>`; }
function fail(e) { main().innerHTML = `<div class="banner"><div><strong>Something went wrong</strong>${esc(e.message)}</div></div>`; }
function bars(rows) {
  const max = Math.max(1, ...rows.map(r => r.n));
  return `<div class="bars" role="img" aria-label="${esc(rows.map(r => `${r.label}: ${r.n}`).join(", "))}">${rows.map(r => `
    <div class="bar-row"><span>${esc(r.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${(r.n / max) * 100}%"></div></div><span class="n">${r.n}</span></div>`).join("")}</div>`;
}
function sourceLink(c) {
  if (!c || !c.url) return `<span class="muted">No source</span>`;
  return `<a href="${esc(safeUrl(c.url))}" target="_blank" rel="noopener noreferrer">${esc(c.source_key || "")} ${esc(c.publisher || c.source_name || new URL(c.url).hostname)}</a>`;
}
function evidenceItem(cl) {
  return `<div class="evidence-item">
    <div>${statusBadge(cl.verification_status, cl.verification_label)} <span class="small muted">claim #${cl.id}</span></div>
    <p><strong>${esc(cl.field.replaceAll("_", " "))}:</strong> ${esc(cl.value_text)}</p>
    ${cl.evidence_excerpt ? `<blockquote class="excerpt">${esc(cl.evidence_excerpt)}</blockquote><p class="small muted">${esc(cl.evidence_locator || "")}</p>`
      : `<p class="small muted">No supporting text stored yet.</p>`}
    <p class="small">Source: ${sourceLink(cl)} · tier ${esc(cl.tier ?? "?")} · ${retBadge(cl.retrieval_status)}
      ${cl.last_retrieval_date ? ` · retrieved ${esc(cl.last_retrieval_date)}` : ""}</p>
    <p class="small muted">${esc(cl.verification_note || "")}</p>
    <button class="btn small" data-claim="${cl.id}">Full evidence record</button></div>`;
}

let DATA_STATE = null;
async function dataBanner() {
  if (!DATA_STATE) DATA_STATE = await api("/api/overview");
  const o = DATA_STATE;
  if (o.claims_verified > 0) return "";
  return `<div class="banner" role="status"><div><strong>No facts are verified yet</strong>
    ${o.sources_retrieved} of ${o.sources} registered sources could be retrieved, so every company, centre and policy shown here
    is a <em>lead</em> found by web search. It is not a confirmed fact. Each record shows its status and the source to check.</div></div>`;
}

// ---------- drawer ----------

function openDrawer(html) {
  $("#drawer-body").innerHTML = html;
  $("#drawer").hidden = false;
  $("#drawer-close").focus();
}
function closeDrawer() { $("#drawer").hidden = true; }
$("#drawer-close").addEventListener("click", closeDrawer);
$("#drawer").addEventListener("click", e => { if (e.target.id === "drawer") closeDrawer(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });

async function showCompany(slug) {
  try {
    const p = await api(`/api/companies/${encodeURIComponent(slug)}`);
    openDrawer(`<h1 id="drawer-title">${esc(p.name)}</h1>
      <p class="muted">${esc(p.industry)} · Headquarters: ${esc(p.hq_country || "not recorded")}</p>
      <h2>India centres</h2>
      ${p.centres.map(c => `<div class="card" style="margin-bottom:12px">
        <h3>${esc(c.city)}, ${esc(c.state)}</h3>
        <p>${opBadge(c.operational_status)} ${statusBadge(c.verification_status, c.verification_label)}</p>
        <p class="small">Functions: ${esc(c.functions || "not recorded")} · Announced: ${esc(c.announced_date || "not recorded")} · Established: ${esc(c.established_date || "not recorded")}</p>
        <details><summary class="small">Evidence (${c.claims.length})</summary>${c.claims.map(evidenceItem).join("")}</details>
      </div>`).join("")}
      <h2>Corporate structure</h2>
      ${p.structure.relationships.length ? structureHtml(p.structure)
        : `<p class="muted">No documented parent–subsidiary relationships are stored. Relationships are added only from filings or annual reports, never guessed from similar names.</p>`}`);
  } catch (e) { openDrawer(`<p>${esc(e.message)}</p>`); }
}

async function showClaim(id) {
  try {
    const c = await api(`/api/claims/${id}`);
    openDrawer(`<h1 id="drawer-title">Evidence record #${c.id}</h1>
      <p>${statusBadge(c.verification_status, c.verification_label)}</p>
      <p class="small muted">${esc(STATUS_HELP[c.verification_status] || "")}</p>
      <table><tbody>
        <tr><th>Claim</th><td>${esc(c.field.replaceAll("_", " "))}: ${esc(c.value_text)}</td></tr>
        <tr><th>About</th><td>${esc(c.subject_type.replace("_", " "))} #${c.subject_id}</td></tr>
        <tr><th>Period described</th><td>${esc(c.as_of_date || "not recorded")}</td></tr>
        <tr><th>Source</th><td>${sourceLink(c)}<br><span class="small muted">${esc(c.source_type)} · tier ${esc(c.tier)}</span></td></tr>
        <tr><th>Published</th><td>${esc(c.publication_date || "unknown")} <span class="small muted">(${esc(c.publication_date_basis || "")})</span></td></tr>
        <tr><th>Retrieval</th><td>${retBadge(c.retrieval_status)} ${c.last_retrieval_date ? `on ${esc(c.last_retrieval_date)}` : ""}</td></tr>
        <tr><th>Supporting text</th><td>${c.evidence_excerpt ? `<blockquote class="excerpt">${esc(c.evidence_excerpt)}</blockquote>${esc(c.evidence_locator || "")}` : "None stored"}</td></tr>
        <tr><th>Reviewer</th><td>${esc(c.reviewed_by || "Not reviewed")} ${esc(c.reviewed_at || "")}</td></tr>
        <tr><th>Note</th><td>${esc(c.verification_note)}</td></tr>
      </tbody></table>
      <h2>History</h2>
      ${c.history.length ? `<ul class="plain">${c.history.map(h => `<li class="small">${esc(h.ts)} — ${esc(h.actor)}: ${esc(h.action)} ${esc(h.detail)}</li>`).join("")}</ul>` : `<p class="muted">No changes recorded since import.</p>`}`);
  } catch (e) { openDrawer(`<p>${esc(e.message)}</p>`); }
}

document.addEventListener("click", e => {
  const claim = e.target.closest("[data-claim]");
  if (claim) { e.preventDefault(); showClaim(claim.dataset.claim); return; }
  const co = e.target.closest("[data-company]");
  if (co) { e.preventDefault(); showCompany(co.dataset.company); }
});
document.addEventListener("keydown", e => {
  if (e.key === "Enter" && e.target.matches("tr[data-company]")) showCompany(e.target.dataset.company);
});

// ---------- pages ----------

const pages = {};

pages.overview = async () => {
  const [o, v, cities, rd] = await Promise.all([api("/api/overview"), api("/api/verification/summary"), api("/api/cities"), api("/api/readiness")]);
  DATA_STATE = o;
  const gatePass = rd.gate.every(g => g.pass);
  main().innerHTML = `
    <h1>India GCC research, backed by evidence</h1>
    <p class="muted">Compare six cities for a Global Capability Centre. Every record links to its source and says how far it has been checked.</p>
    <form class="searchbox" id="hero-search" role="search"><input type="search" placeholder="Search a company, e.g. Mastercard" aria-label="Search companies" maxlength="100"></form>
    ${await dataBanner()}
    <div class="grid">
      ${stat(o.companies, "Companies tracked", { meaning: "Companies with at least one India centre record in the database.", source: "Chosen in research Phase 1 for public source availability.", period: "Selected October 2026.", check: "Company selection is documented; centre facts are checked separately." })}
      ${stat(o.centre_records, "Centre records", { meaning: "Company-and-city records, including unconfirmed leads.", source: "Web-search discovery, then source retrieval.", period: "As discovered, October 2026.", check: `${o.centres_verified} confirmed against source text.` })}
      ${stat(`${o.sources_retrieved} / ${o.sources}`, "Sources retrieved", { meaning: "Registered sources whose text was downloaded and stored.", source: "Source register and ingestion job log.", period: "Latest ingestion run.", check: "Each attempt is logged with its HTTP result." })}
      ${stat(`${o.claims_verified} / ${o.claims}`, "Claims verified", { meaning: "Facts confirmed by a person against retrieved source text.", source: "Claims table.", period: "Current.", check: "Automated text match, then human review." })}
    </div>
    <h2>How far each claim has been checked</h2>
    <div class="card">${bars(v.claims_by_status.map(s => ({ label: s.label, n: s.count })))}
      <p class="small muted">Counts of all ${o.claims} stored claims by verification status. Live from the database.</p></div>
    <h2>Cities</h2>
    <div class="grid">${cities.map(c => `<a class="card clickable" style="text-decoration:none;color:inherit" href="#/explorer?city=${encodeURIComponent(c.name)}">
      <h3>${esc(c.name)}</h3><p class="muted small">${esc(c.state)}</p>
      <p class="small">${c.centre_records} centre record(s), ${c.verified_centres || 0} verified</p></a>`).join("")}</div>
    <p class="small muted">Centre counts describe this research sample of ${o.companies} companies, not the whole market.</p>
    <h2>Data readiness</h2>
    <div class="card"><p>${gatePass ? `<span class="badge ok">Gate passed</span>` : `<span class="badge warn">Gate not passed</span>`}
      ${rd.gate.filter(g => g.pass).length} of ${rd.gate.length} checks pass.</p>
      <a href="#/evidence">See checks and data quality →</a></div>`;
  $("#hero-search").addEventListener("submit", e => { e.preventDefault(); location.hash = `#/explorer?q=${encodeURIComponent(e.target.querySelector("input").value)}`; });
};

pages.explorer = async (params) => {
  const [cities, inds] = await Promise.all([api("/api/cities"), api("/api/industries")]);
  const state = { q: params.get("q") || "", city: params.get("city") || "", status: "", verification: "", industry: "" };
  main().innerHTML = `
    <h1>GCC Explorer</h1>
    <p class="muted">Find GCC centres by company, city or industry. Select a row to see the evidence.</p>
    <form class="searchbox" id="ex-search" role="search"><input type="search" value="${esc(state.q)}" placeholder="Search company, centre or function" aria-label="Search centres" maxlength="100"></form>
    <div class="chips" role="group" aria-label="City"><button class="chip" data-city="" aria-pressed="${!state.city}">All cities</button>
      ${cities.map(c => `<button class="chip" data-city="${esc(c.name)}" aria-pressed="${state.city === c.name}">${esc(c.name)}</button>`).join("")}</div>
    <div class="filters">
      <label>Status<select id="f-status"><option value="">Any</option>${Object.entries(OP_LABEL).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
      <label>Verification<select id="f-ver"><option value="">Any</option>${Object.keys(STATUS_CLASS).map(k => `<option value="${k}">${k.replaceAll("_", " ")}</option>`).join("")}</select></label>
      <label>Industry<select id="f-ind"><option value="">Any</option>${inds.map(i => `<option>${esc(i)}</option>`).join("")}</select></label>
    </div>
    ${await dataBanner()}
    <div id="ex-results"></div>`;
  const render = async () => {
    const out = $("#ex-results");
    if (!out) return;
    try {
      const rows = await api(`/api/centres?${qs(state)}`);
      if (!$("#ex-results")) return;      out.innerHTML = rows.length ? `<p class="small muted">${rows.length} result(s)</p><div class="table-wrap"><table class="stack">
        <thead><tr><th>Company</th><th>City</th><th>Industry</th><th>Status</th><th>Verification</th><th>Sources</th></tr></thead>
        <tbody>${rows.map(r => `<tr class="clickable" tabindex="0" data-company="${esc(r.company_slug)}">
          <td data-label="Company">${esc(r.company)}</td><td data-label="City">${esc(r.city)}</td><td data-label="Industry">${esc(r.industry)}</td>
          <td data-label="Status">${opBadge(r.operational_status)}</td>
          <td data-label="Verification">${statusBadge(r.verification_status, r.verification_label)}</td><td data-label="Sources">${r.claim_count}</td></tr>`).join("")}</tbody></table></div>`
        : empty("No centres match these filters.");
    } catch (e) { out.innerHTML = empty(esc(e.message)); }
  };
  $("#ex-search").addEventListener("submit", e => { e.preventDefault(); state.q = e.target.querySelector("input").value.trim(); render(); });
  main().querySelectorAll("[data-city]").forEach(b => b.addEventListener("click", () => {
    state.city = b.dataset.city;
    main().querySelectorAll("[data-city]").forEach(x => x.setAttribute("aria-pressed", x === b));
    render();
  }));
  $("#f-status").addEventListener("change", e => { state.status = e.target.value; render(); });
  $("#f-ver").addEventListener("change", e => { state.verification = e.target.value; render(); });
  $("#f-ind").addEventListener("change", e => { state.industry = e.target.value; render(); });
  render();
};

pages.compare = async (params) => {
  const cities = await api("/api/cities");
  const chosen = new Set((params.get("cities") || "Bengaluru,Hyderabad").split(",").filter(c => cities.some(x => x.name === c)));
  main().innerHTML = `
    <h1>City Comparison</h1>
    <p class="muted">Choose 2 to 6 cities. Costs are compared only when the figures use the same unit, period, currency and building grade, and are verified.</p>
    <div class="chips" role="group" aria-label="Cities to compare">${cities.map(c => `<button class="chip" data-c="${esc(c.name)}" aria-pressed="${chosen.has(c.name)}">${esc(c.name)}</button>`).join("")}</div>
    ${await dataBanner()}
    <div id="cmp"></div>`;
  const render = async () => {
    const out = $("#cmp");
    if (!out) return;
    if (chosen.size < 2) { out.innerHTML = empty("Pick at least two cities."); return; }
    try {
      const r = await api(`/api/cities/compare?${qs({ cities: [...chosen] })}`);
      if (!$("#cmp")) return;      out.innerHTML = `<div class="cols">${r.cities.map(c => `<div class="card">
          <h3>${esc(c.name)}</h3><p class="muted small">${esc(c.state)}</p>
          <p class="small"><strong>Centre records:</strong> ${Object.entries(c.centres_by_status).map(([k, v]) => `${v} ${esc((OP_LABEL[k] || k).toLowerCase())}`).join(", ") || "none"}</p>
          <p class="small"><strong>Companies:</strong> ${c.companies.map(esc).join(", ") || "none recorded"}</p>
          <p class="small"><strong>State policies:</strong></p>
          <ul class="plain small">${c.policies.map(p => `<li><a href="#/policies?state=${encodeURIComponent(c.state)}">${esc(p.name)}</a> ${statusBadge(p.verification_status, p.verification_label)}</li>`).join("") || "<li class='muted'>None recorded</li>"}</ul>
          <p class="small"><strong>Talent indicators:</strong> ${c.talent_observations.length || "none stored"}</p>
        </div>`).join("")}</div>
        <h2>Costs</h2>
        ${r.comparable_cost_groups.length ? r.comparable_cost_groups.map(g => `<div class="card" style="margin-bottom:12px">
            <h3>${esc(g.category.replaceAll("_", " "))} — ${esc(g.currency)} ${esc(g.unit)}, ${esc(g.period.replace("_", " "))}${g.building_category ? `, ${esc(g.building_category)}` : ""}</h3>
            ${bars(g.observations.map(o => ({ label: `${o.city} (${o.period_start})`, n: o.value_num })))}
            <p class="small muted">Sources: ${g.observations.map(o => `<a href="${esc(safeUrl(o.url))}" target="_blank" rel="noopener">${esc(o.source_key)}</a>`).join(", ")}</p></div>`).join("")
          : empty(`No cost chart is shown: there are no verified cost figures that can be fairly compared across these cities.
              ${r.noncomparable_cost_observations ? `${r.noncomparable_cost_observations} observation(s) exist but use different units, periods or methods.` : "No cost observations are stored yet."}`)}`;
    } catch (e) { out.innerHTML = empty(esc(e.message)); }
  };
  main().querySelectorAll("[data-c]").forEach(b => b.addEventListener("click", () => {
    const n = b.dataset.c;
    if (chosen.has(n)) chosen.delete(n); else if (chosen.size < 6) chosen.add(n);
    b.setAttribute("aria-pressed", chosen.has(n));
    history.replaceState(null, "", `#/compare?cities=${encodeURIComponent([...chosen].join(","))}`);
    render();
  }));
  render();
};

function structureHtml(s) {
  return `<div class="table-wrap"><table><thead><tr><th>Parent</th><th>Relationship</th><th>Child</th><th>Since</th><th>Evidence</th></tr></thead><tbody>
    ${s.relationships.map(r => `<tr><td>${esc(r.parent_name)} <span class="muted small">${esc(r.parent_jurisdiction)}</span></td>
      <td>${esc(r.relationship_type.replaceAll("_", " "))}</td><td>${esc(r.child_name)} <span class="muted small">${esc(r.child_jurisdiction)}</span></td>
      <td>${esc(r.effective_date || "—")}</td><td>${statusBadge(r.verification_status, r.verification_label)} ${r.url ? `<a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">${esc(r.source_key)}</a>` : ""}</td></tr>`).join("")}
    </tbody></table></div>`;
}

pages.groups = async () => {
  const groups = await api("/api/groups");
  const total = groups.reduce((a, g) => a + g.relationships, 0);
  main().innerHTML = `
    <h1>Company Groups</h1>
    <p class="muted">How each parent company holds its Indian operations. Links are recorded only from filings, annual reports or official statements. They are never inferred from similar names.</p>
    ${total === 0 ? `<div class="banner info"><div><strong>No group structures documented yet</strong>
      The sources that show legal ownership (annual-report subsidiary lists, Indian company filings) have not been retrieved. This page fills in as they are.</div></div>` : ""}
    <div class="table-wrap"><table><thead><tr><th>Company</th><th>Industry</th><th>Entities</th><th>Documented relationships</th></tr></thead>
      <tbody>${groups.map(g => `<tr class="clickable" tabindex="0" data-company="${esc(g.slug)}"><td>${esc(g.name)}</td><td>${esc(g.industry)}</td><td>${g.entities}</td><td>${g.relationships}</td></tr>`).join("")}</tbody></table></div>`;
};

pages.policies = async (params) => {
  const all = await api("/api/policies");
  const states = [...new Set(all.map(p => p.state))];
  let sel = params.get("state") || "";
  main().innerHTML = `
    <h1>Policies &amp; Incentives</h1>
    <p class="muted">State GCC policies and central rules. Benefit amounts are shown only when taken from the official text. This is research, not legal or tax advice.</p>
    <div class="chips" role="group" aria-label="State">${["", ...states].map(s => `<button class="chip" data-s="${esc(s)}" aria-pressed="${sel === s}">${esc(s || "All")}</button>`).join("")}</div>
    ${await dataBanner()}
    <div id="pol"></div>`;
  const render = async () => {
    const out = $("#pol");
    if (!out) return;
    const rows = all.filter(p => !sel || p.state === sel);
    const details = await Promise.all(rows.map(p => api(`/api/policies/${p.id}`)));
    if (!$("#pol") || $("#pol") !== out) return;
    out.innerHTML = details.map(p => `<div class="card" style="margin-bottom:16px">
      <h3>${esc(p.name)}</h3>
      <p class="small muted">${esc(p.state)} · ${esc(p.issuing_authority || "Issuer not recorded")} · ${esc(p.policy_kind.replaceAll("_", " "))}</p>
      <p><span class="badge">${esc(p.status.replaceAll("_", " "))}</span> ${statusBadge(p.verification_status, p.verification_label)}</p>
      <p class="small">${esc(p.notes)}</p>
      <h3 style="margin-top:12px">Versions</h3>
      <ul class="plain small">${p.versions.map(v => `<li><strong>${esc(v.version_label)}</strong> — effective ${esc(v.effective_date || "not confirmed")}, expires ${esc(v.expiry_date || "not confirmed")}
        · <a href="${esc(safeUrl(v.url))}" target="_blank" rel="noopener">${esc(v.source_key)} ${esc(v.publisher)}</a> ${retBadge(v.retrieval_status)}
        ${v.incentives.length ? `<div class="table-wrap" style="margin-top:6px"><table><thead><tr><th>Benefit</th><th>Amount / formula</th><th>Cap</th><th>Eligibility</th><th>Status</th></tr></thead><tbody>
          ${v.incentives.map(i => `<tr><td>${esc(i.benefit_type)}</td><td>${esc(i.amount_or_formula || "—")}</td><td>${esc(i.cap || "—")}</td><td>${esc(i.eligibility || "—")}</td><td>${statusBadge(i.verification_status, i.verification_label)}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="muted">No incentive terms stored. They will be added from the official text once it is retrieved.</div>`}</li>`).join("")}</ul>
      <details><summary class="small">Evidence (${p.claims.length})</summary>${p.claims.map(evidenceItem).join("")}</details>
    </div>`).join("") || empty("No policies for this state.");
  };
  main().querySelectorAll("[data-s]").forEach(b => b.addEventListener("click", () => {
    sel = b.dataset.s;
    main().querySelectorAll("[data-s]").forEach(x => x.setAttribute("aria-pressed", x === b));
    render();
  }));
  render();
};

pages.evidence = async () => {
  const [v, q, rd, sources] = await Promise.all([api("/api/verification/summary"), api("/api/quality"), api("/api/readiness"), api("/api/sources")]);
  const sevClass = { high: "bad", medium: "warn" };
  main().innerHTML = `
    <h1>Evidence &amp; Verification</h1>
    <p class="muted">How every record was checked, which sources were read, and what the automated quality checks found.</p>
    <h2>Verification status</h2>
    <div class="card">${bars(v.claims_by_status.map(s => ({ label: s.label, n: s.count })))}
      <details class="explain"><summary>What do these statuses mean?</summary><dl>
        ${Object.entries(STATUS_HELP).map(([k, t]) => `<dt>${esc(k.replaceAll("_", " "))}</dt><dd>${esc(t)}</dd>`).join("")}</dl></details></div>
    <h2>Data readiness gate</h2>
    <div class="table-wrap"><table><thead><tr><th>Check</th><th>Result</th><th>Evidence</th></tr></thead><tbody>
      ${rd.gate.map(g => `<tr><td>${esc(g.criterion)}</td><td>${g.pass ? `<span class="badge ok">Pass</span>` : `<span class="badge bad">Fail</span>`}</td><td class="small">${esc(g.evidence)}</td></tr>`).join("")}
    </tbody></table></div>
    <h2>Data Quality Center</h2>
    <p class="small muted">Automated checks run live against the database. They flag problems and never approve a record.</p>
    <div class="table-wrap"><table><thead><tr><th>Check</th><th>Severity</th><th>Flagged</th></tr></thead><tbody>
      ${q.map(c => `<tr><td>${esc(c.label)}${c.count ? `<details><summary class="small">Show records</summary><pre class="small" style="white-space:pre-wrap">${esc(c.rows.slice(0, 10).map(r => JSON.stringify(r)).join("\n"))}</pre></details>` : ""}</td>
        <td><span class="badge ${sevClass[c.severity] || ""}">${esc(c.severity)}</span></td><td>${c.count}</td></tr>`).join("")}
    </tbody></table></div>
    <h2>Sources (${sources.length})</h2>
    <p class="small muted">Tier 1–2 company, 3 government, 4 industry body, 5 real-estate research, 6 news and advisory, 7 discovery only.</p>
    <div class="table-wrap"><table><thead><tr><th>ID</th><th>Source</th><th>Tier</th><th>Published</th><th>Retrieval</th></tr></thead><tbody>
      ${sources.map(s => `<tr><td>${esc(s.source_key)}</td><td><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.name)}</a><br><span class="small muted">${esc(s.publisher)}</span></td>
        <td>${s.tier}</td><td class="small">${esc(s.publication_date || "unknown")}</td><td>${retBadge(s.retrieval_status)}<br><span class="small muted">${esc(s.last_retrieval_attempt || "")}</span></td></tr>`).join("")}
    </tbody></table></div>`;
};

pages.assistant = async () => {
  const examples = ["Which companies have GCCs in Pune?", "What incentives does Haryana offer?", "What is office rent in Bengaluru?", "Goldman Sachs Hyderabad"];
  main().innerHTML = `
    <h1>Research Assistant</h1>
    <p class="muted">Ask a question in plain words. Answers come only from records in the database, and each one shows its source and how far it has been checked.</p>
    <form class="searchbox" id="ra-form"><input id="ra-q" type="search" placeholder="e.g. Which state policies apply to Noida?" aria-label="Your question" minlength="3" maxlength="500"></form>
    <div class="chips">${examples.map(x => `<button class="chip" data-ex="${esc(x)}">${esc(x)}</button>`).join("")}</div>
    <div id="ra-out"></div>`;
  const ask = async q => {
    const out = $("#ra-out");
    if (!out) return;
    if (q.length < 3) { out.innerHTML = empty("Please type a longer question."); return; }
    out.innerHTML = `<p class="muted">Searching…</p>`;
    try {
      const r = await api("/api/research", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      if (!$("#ra-out")) return;
      const u = r.understood;
      out.innerHTML = `<div class="card">
        <p><strong>${esc(r.summary)}</strong></p>
        <p class="small muted">Understood — cities: ${esc(u.cities.join(", ") || "none")}; states: ${esc(u.states.join(", ") || "none")}; companies: ${esc(u.companies.join(", ") || "none")}; topics: ${esc(u.topics.join(", ") || "none")}</p>
        ${r.gaps.length ? `<h3 style="margin-top:12px">What the data does not cover</h3><ul>${r.gaps.map(g => `<li>${esc(g)}</li>`).join("")}</ul>` : ""}
        ${r.findings.length ? `<h3 style="margin-top:12px">Records found</h3>${r.findings.map(f => `<div class="evidence-item">
            <p>${esc(f.text)}</p>${f.evidence ? `<blockquote class="excerpt">${esc(f.evidence)}</blockquote>` : ""}
            <p class="small">${statusBadge(f.citation.status, f.citation.status_label)} Source: ${sourceLink(f.citation)}</p></div>`).join("")}` : ""}
        <p class="small muted">${esc(r.disclaimer)}</p></div>`;
    } catch (e) { out.innerHTML = empty(esc(e.message)); }
  };
  $("#ra-form").addEventListener("submit", e => { e.preventDefault(); ask($("#ra-q").value.trim()); });
  main().querySelectorAll("[data-ex]").forEach(b => b.addEventListener("click", () => { $("#ra-q").value = b.dataset.ex; ask(b.dataset.ex); }));
};

// ---------- router ----------

let _routeVersion = 0;
function routeVersion() { return _routeVersion; }

async function route() {
  const ver = ++_routeVersion;
  const [path, query] = (location.hash.slice(2) || "overview").split("?");
  const page = pages[path] ? path : "overview";
  document.querySelectorAll(".rail a").forEach(a => a.classList.toggle("active", a.dataset.page === page));
  document.querySelectorAll(".rail a").forEach(a => a.toggleAttribute("aria-current", a.dataset.page === page));
  closeDrawer();
  loading();
  try { await pages[page](new URLSearchParams(query || "")); } catch (e) { if (ver === _routeVersion) fail(e); }
  if (ver === _routeVersion) document.title = `${$(".rail a.active")?.textContent || "Overview"} · GCC Atlas`;
}
window.addEventListener("hashchange", route);
$("#topsearch").addEventListener("submit", e => {
  e.preventDefault();
  location.hash = `#/explorer?q=${encodeURIComponent($("#topsearch-input").value.trim())}`;
});
route();
