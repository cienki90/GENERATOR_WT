"use strict";
// Generator WT - interfejs okna. Logika programu jest w Pythonie (web/api.py); tutaj tylko
// widok: mapa (OpenLayers w układzie PL-2000 projektu), wykaz, kontrola i ustawienia.
// Dane z rysunku i usług wstawiamy zawsze jako tekst (textContent), nigdy jako HTML.
(() => {
  const TOKEN = new URLSearchParams(location.search).get("t") || "";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const WMS = {
    orto: ["https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution", "Raster", false,
           "Ortofotomapa © GUGiK"],
    topo: ["https://mapy.geoportal.gov.pl/wss/service/img/guest/TOPO/MapServer/WMSServer", "Raster", false,
           "Mapa topograficzna © GUGiK"],
    egib: ["https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow",
           "dzialki,numery_dzialek,budynki", true, "EGiB © GUGiK / powiaty"],
    gesut: ["https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaUzbrojeniaTerenu",
            "przewod_telekomunikacyjny,przewod_elektroenergetyczny,przewod_gazowy,przewod_wodociagowy," +
            "przewod_kanalizacyjny,przewod_cieplowniczy,przewod_niezidentyfikowany,przewod_urzadzenia", true,
            "GESUT © GUGiK / powiaty"],
  };
  const KOLUMNY = [ // [nagłówek, pole, edytowalne, liczba]
    ["W num.", "_wl"], ["Nr", "etykieta"], ["Stacja trafo", "stacja"], ["Nr w sieci", "nr_w_sieci", true],
    ["Miejscowość", "miejscowosc", true], ["Ulica", "ulica", true], ["Droga przy słupie", "ulica_droga"],
    ["Gmina", "gmina", true], ["Rejon", "rejon"], ["Rodzaj", "rodzaj_slupa", true],
    ["Typ słupa", "typ_slupa", true], ["X (2000)", "geo_x", false, true], ["Y (2000)", "geo_y", false, true],
    ["Działka", "dzialka"], ["Uwagi", "uwagi", true],
  ];
  const POLA_OPERATORA = ["Nazwa", "Numer Umowy Ramowej", "Pełna nazwa", "Adres (siedziba)", "Kod pocztowy",
                          "NIP", "Regon", "Numer wpisu do RPT", "Dane kontaktowe"];

  const S = {
    dane: null, zazn: null, praca: null, nrZd: 0, dialogi: false, plikUstawien: null,
    mapa: null, kod: null, warstwy: {}, wygenerowano: false, start: null, polaczenie: true,
  };

  // ------------------------------------------------------------------ pomocnicze
  function el(tag, wl = {}, ...dzieci) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(wl)) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (k === "dataset") Object.assign(e.dataset, v);
      else if (k in e && typeof v !== "string") e[k] = v;
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const d of dzieci.flat()) if (d != null && d !== false) e.append(d instanceof Node ? d : String(d));
    return e;
  }
  async function rpc(metoda, args = {}) {
    let odp;
    try {
      odp = await fetch(`/api/${metoda}`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-Token": TOKEN },
        body: JSON.stringify({ args }),
      });
    } catch (e) { throw new Error("Brak połączenia z programem."); }
    const d = await odp.json();
    if (!d.ok) throw new Error(d.blad || "Nieznany błąd.");
    return d.wynik;
  }
  const bezpiecznie = (fn) => async (...a) => {
    try { return await fn(...a); } catch (e) { await komunikat("Nie udało się", e.message); }
  };
  function odczekaj(fn, ms) {
    let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }
  const kolor = (nazwa) => getComputedStyle(document.documentElement).getPropertyValue(nazwa).trim();
  const dataPL = (iso) => (iso && /^\d{4}-\d\d-\d\d$/.test(iso)) ? iso.split("-").reverse().join(".") : "";
  const dataISO = (pl) => (pl && /^\d\d\.\d\d\.\d{4}$/.test(pl)) ? pl.split(".").reverse().join("-") : "";
  const slup = (id) => S.dane && S.dane.slupy[id];
  const pamiec = {
    czytaj(k, dom) { try { const v = localStorage.getItem("wt." + k); return v == null ? dom : JSON.parse(v); } catch (e) { return dom; } },
    zapisz(k, v) { try { localStorage.setItem("wt." + k, JSON.stringify(v)); } catch (e) { /* bez pamięci */ } },
  };

  // ------------------------------------------------------------------ pasek stanu, dziennik
  function status(t) { $("#status").textContent = t; }
  function log(t) {
    const d = $("#dziennik");
    d.textContent += t + "\n";
    if (d.textContent.length > 400000) d.textContent = d.textContent.slice(-300000);
    d.parentElement.scrollTop = d.parentElement.scrollHeight;
    const pierwsza = String(t).split("\n")[0];
    if (pierwsza && !pierwsza.startsWith("Traceback")) status(pierwsza);
  }
  function postep(i, n, opis) {
    const p = $("#postep");
    p.classList.remove("ukryte");
    p.classList.toggle("nieokreslony", !n);
    $("#pasek").style.width = n ? `${Math.round(100 * i / n)}%` : "";
    if (opis) status(opis);
  }

  // ------------------------------------------------------------------ praca w tle
  function ustawPrace(nazwa) {
    S.praca = nazwa || null;
    document.body.classList.toggle("zajety", !!S.praca);
    $$("#lewy input, #lewy select, #lewy button, #przyjmij-ulice").forEach((x) => { x.disabled = !!S.praca; });
    if (!S.praca) {
      $("#postep").classList.add("ukryte");
      zaleznosciWynikow();
    } else postep(0, 0);
    odswiezKarte();
  }
  async function petla() {
    try {
      const z = await rpc("zdarzenia", { od: S.nrZd });
      if (!S.polaczenie) { S.polaczenie = true; status("Połączono z programem"); }
      if ((z.praca || null) !== S.praca && !z.zdarzenia.some((e) => e.typ === "koniec")) ustawPrace(z.praca);
      for (const e of z.zdarzenia) {
        S.nrZd = e.nr;
        if (e.typ === "log") log(e.tekst);
        else if (e.typ === "postep") postep(e.i, e.n, e.opis);
        else if (e.typ === "koniec") await koniecPracy(e);
      }
    } catch (e) {
      if (S.polaczenie) { S.polaczenie = false; status("Brak połączenia z programem – czy okno programu jest otwarte?"); }
    }
    setTimeout(petla, S.praca ? 250 : 800);
  }
  async function koniecPracy(e) {
    ustawPrace(null);
    if (!e.ok) {
      status(`Błąd: ${e.blad}`);
      await komunikat(e.zadanie === "analiza" ? "Błąd analizy" : "Nie udało się", e.blad);
      return;
    }
    if (e.zadanie === "analiza") {
      S.zazn = null;
      await zaladujDane(true);
      const b = e.wynik && e.wynik.bledy_geokodowania;
      if (b) status(`Bez adresu (błąd usługi): ${b} słupów – uruchom analizę ponownie.`);
      const problemy = S.dane.kontrola.filter((s) => s.poziom === "blad" || s.poziom === "ostrz").length;
      if (problemy) $("#prawy").scrollTop = 0;
    } else if (e.zadanie === "arkusze") {
      await zaladujDane(false);
    } else if (e.zadanie === "generuj") {
      S.wygenerowano = !e.wynik.bledy.length;
      renderKroki();
      await oknoWynikow(e.wynik);
    }
  }

  // ------------------------------------------------------------------ ustawienia
  function ustawienia() {
    return {
      prefiks: $("#prefiks").value.trim(), numer_startowy: parseInt($("#numer-startowy").value, 10) || 0,
      tolerancja_slupa: parseFloat($("#tolerancja").value) || 5, zakladka: parseFloat($("#zakladka").value) || 0,
      inteligentny_kierunek: $("#kierunek").checked, operator: $("#operator").value, rejon: $("#rejon").value,
      umowa_od: dataPL($("#umowa-od").value), umowa_do: $("#umowa-do").value.trim(),
    };
  }
  function zastosujUstawienia(u) {
    if (!u) return;
    if ("prefiks" in u) $("#prefiks").value = u.prefiks;
    if ("numer_startowy" in u) $("#numer-startowy").value = u.numer_startowy;
    if ("tolerancja_slupa" in u) $("#tolerancja").value = u.tolerancja_slupa;
    if ("zakladka" in u) $("#zakladka").value = u.zakladka;
    if ("inteligentny_kierunek" in u) $("#kierunek").checked = !!u.inteligentny_kierunek;
    if (u.operator && [...$("#operator").options].some((o) => o.value === u.operator)) $("#operator").value = u.operator;
    if (u.rejon && [...$("#rejon").options].some((o) => o.value === u.rejon)) $("#rejon").value = u.rejon;
    if (u.umowa_od && dataISO(u.umowa_od)) $("#umowa-od").value = dataISO(u.umowa_od);
    if ("umowa_do" in u) $("#umowa-do").value = u.umowa_do;
  }
  function wyniki() {
    const w = {};
    $$("[data-wynik]").forEach((c) => { w[c.dataset.wynik] = c.checked; });
    return w;
  }
  function zaleznosciWynikow() {
    if (S.praca) return;
    const w = wyniki();
    $('[data-wynik="arkusze"]').disabled = !w.dxf;
    $('[data-wynik="pdf_numeracji"]').disabled = !(w.dxf && w.arkusze);
    $$("#orientacja-opcje input, #orientacja-opcje select").forEach((x) => { x.disabled = !w.orientacja; });
  }
  function opcje() {
    const w = wyniki();
    return {
      ...w, arkusze: w.dxf && w.arkusze, pdf_numeracji: w.dxf && w.arkusze && w.pdf_numeracji,
      orientacja_opcje: {
        skala: parseInt($("#or-skala").value, 10), zrodlo: $("#or-zrodlo").value, szarosc: $("#or-szarosc").checked,
        trasa: $("#or-trasa").checked, pdf: $("#or-pdf").checked,
      },
      katalog: $("#katalog").value.trim(), operator: $("#operator").value, rejon: $("#rejon").value,
      opracowal: $("#opracowal").value.trim(), data_rysunku: $("#data-rysunku").value.trim(),
      umowa_od: dataPL($("#umowa-od").value), umowa_do: $("#umowa-do").value.trim() || "-",
      tolerancja_slupa: parseFloat($("#tolerancja").value) || 5, ustawienia: ustawienia(), wyniki: w,
    };
  }
  function wypelnijListy(sl, operator, rejon) {
    for (const [sel, lista, wyb] of [["#operator", sl.operatorzy, operator], ["#rejon", sl.rejony, rejon]]) {
      const s = $(sel);
      const poprz = wyb || s.value;
      s.replaceChildren(...lista.map((n) => el("option", { value: n, text: n })));
      if (lista.includes(poprz)) s.value = poprz;
    }
  }

  // ------------------------------------------------------------------ analiza
  const analizuj = bezpiecznie(async () => {
    if (S.praca) return;
    const plik = $("#plik").value.trim().replace(/^"|"$/g, "");
    if (!plik) {
      await komunikat("Wybierz projekt", "Wskaż plik DXF projektu (przycisk „Wybierz…” albo wpisz ścieżkę).");
      return;
    }
    $("#plik").value = plik;
    if (plik !== S.plikUstawien) {
      const u = await rpc("ustawienia_projektu_dla", { plik });
      if (Object.keys(u).length) { zastosujUstawienia(u); log("Wczytano ustawienia zapamiętane dla projektu."); }
      S.plikUstawien = plik;
    }
    await rpc("analizuj", { plik, geokodowanie: $("#geo").checked, ustawienia: ustawienia() });
    ustawPrace("analiza");
  });
  const wybierzPlik = bezpiecznie(async () => {
    if (S.praca) return;
    const r = await rpc("wybierz_plik", { start: $("#plik").value.trim() });
    if (r.brak_dialogu) { $("#plik").focus(); status("Wpisz ścieżkę pliku DXF i naciśnij Enter."); return; }
    if (r.plik) { $("#plik").value = r.plik; await analizuj(); }
  });
  async function zaladujDane(dopasuj) {
    S.dane = await rpc("dane");
    if (S.zazn != null && !slup(S.zazn)) S.zazn = null;
    renderuj(dopasuj);
  }
  const przelicz = bezpiecznie(async () => {
    if (!S.dane || S.praca) return;
    S.dane = await rpc("przelicz", { ustawienia: ustawienia() });
    renderuj(false);
  });
  const przeliczArkusze = odczekaj(bezpiecznie(async () => {
    if (!S.dane) return;
    if (S.praca) { przeliczArkusze(); return; }
    await rpc("przelicz_arkusze", { ustawienia: ustawienia() });
    ustawPrace("arkusze");
  }), 600);

  async function zmien(metoda, args) {
    if (S.praca) { status("Program pracuje – poczekaj na zakończenie."); return; }
    try {
      const przewin = $(".tresc[data-tresc=wykaz]").scrollTop;
      S.dane = await rpc(metoda, args);
      renderuj(false);
      $(".tresc[data-tresc=wykaz]").scrollTop = przewin;
    } catch (e) { await komunikat("Nie udało się", e.message); }
  }

  // ------------------------------------------------------------------ renderowanie
  function renderuj(dopasuj) {
    const d = S.dane;
    $("#nazwa-pliku").textContent = d ? `${d.nazwa}${d.epsg ? ` · EPSG:${d.epsg}` : ""}` : "Nie wczytano projektu";
    $("#nazwa-pliku").title = d ? d.plik : "";
    $("#pusta-mapa").classList.toggle("ukryte", !!d);
    renderPodsumowanie();
    renderKontrola();
    renderWykaz();
    renderArkusze();
    renderMapa(dopasuj);
    odswiezKarte();
    renderKroki();
    sprawdzTolerancje();
  }
  function renderPodsumowanie() {
    const d = S.dane, p = $("#podsumowanie"), m = $("#metryki");
    if (!d) { p.replaceChildren(); m.replaceChildren(); return; }
    const s = d.podsumowanie;
    p.replaceChildren("Słupów ", el("b", { text: s.slupy }), " · stref trafo ", el("b", { text: s.stacje }),
                      " · błędnych klików ", el("b", { text: s.bledne_kliki }));
    const met = (e, w) => el("div", { class: "metryka" }, el("div", { class: "etykieta", text: e }),
                             el("div", { class: "wartosc", text: w }));
    m.replaceChildren(met("Słupy w numeracji", `${s.plan} / ${s.slupy}`), met("Arkusze 1:1000", s.arkusze),
                      met("Stacje trafo", s.stacje), met("Wyłączone", s.wykluczone));
  }
  function renderKontrola() {
    const k = $("#kontrola");
    if (!S.dane) { k.replaceChildren(el("p", { class: "wyszarzone", text: "Brak projektu." })); return; }
    let problemy = 0;
    const sekcje = S.dane.kontrola.map((s) => {
      if (s.poziom === "blad" || s.poziom === "ostrz") problemy += s.pozycje.length || 1;
      const det = el("details", { class: `sekcja p-${s.poziom}`, open: (s.poziom === "blad" || s.poziom === "ostrz") && s.pozycje.length <= 40 },
        el("summary", {}, el("span", { class: "kropka" }),
           el("span", { class: "t" }, s.tytul, el("span", { class: "o", text: s.opis }))));
      if (s.pozycje.length) {
        det.append(el("div", { class: "pozycje" }, s.pozycje.map((p) =>
          el(p.slupy.length ? "button" : "div", {
            class: `pozycja p-${p.poziom}`, title: p.slupy.length ? "Pokaż na mapie" : null,
            onclick: p.slupy.length ? () => pokazSlupy(p.slupy, p.odcinek) : null,
          }, el("span", { class: "t", text: p.tytul }), p.szczegoly ? el("span", { class: "s", text: p.szczegoly }) : null))));
      }
      return det;
    });
    k.replaceChildren(...sekcje);
    $("#licznik-problemow").textContent = problemy ? `${problemy} do sprawdzenia` : "wszystko w porządku";
    const ulice = S.dane.kontrola.find((s) => s.id === "ulice");
    $("#przyjmij-ulice").classList.toggle("ukryte", !(ulice && ulice.pozycje.length));
  }
  function renderKroki() {
    const d = S.dane;
    const problemy = d ? d.kontrola.some((s) => s.poziom === "blad" || s.poziom === "ostrz") : false;
    const stan = {
      projekt: d ? "gotowy" : "", kontrola: d ? (problemy ? "uwaga" : "gotowy") : "",
      zlecenie: d && $("#operator").value ? "gotowy" : "", wyniki: S.wygenerowano ? "gotowy" : "",
    };
    let biezacy = ["projekt", "zlecenie", "wyniki"].find((k) => stan[k] !== "gotowy");
    if (d && biezacy === "zlecenie" && problemy) biezacy = "kontrola";
    $$(".krok").forEach((b) => {
      const k = b.dataset.krok;
      b.className = `krok ${stan[k]} ${k === biezacy ? "biezacy" : ""}`;
    });
  }

  // ------------------------------------------------------------------ wykaz
  function wartosc(s, pole) {
    const v = s[pole];
    if (v == null) return "";
    return typeof v === "number" ? v.toFixed(2) : String(v);
  }
  function renderWykaz() {
    const t = $("#wykaz");
    if (!S.dane) { t.replaceChildren(); return; }
    const filtr = $("#filtr").value.trim().toLowerCase();
    const glowa = el("thead", {}, el("tr", {}, KOLUMNY.map(([n]) => el("th", { text: n }))));
    const cialo = el("tbody");
    for (const id of S.dane.kolejnosc) {
      const s = slup(id);
      if (filtr && !KOLUMNY.some(([, p]) => wartosc(s, p).toLowerCase().includes(filtr))) continue;
      const tr = el("tr", { dataset: { id }, class: [s.wykluczony ? "wylaczony" : "", s.id === S.zazn ? "zaznaczony" : ""].join(" ") });
      for (const [, pole, edyt, liczba] of KOLUMNY) {
        if (pole === "_wl") {
          tr.append(el("td", {}, el("input", {
            type: "checkbox", checked: !s.wykluczony, title: "Odznacz, aby wyłączyć słup z numeracji i dokumentów",
            onclick: (e) => e.stopPropagation(),
            onchange: () => zmien("przelacz_wykluczenie", { id: s.id }),
          })));
          continue;
        }
        const td = el("td", { text: wartosc(s, pole), class: [edyt ? "edyt" : "", liczba ? "liczba" : "",
          pole === "uwagi" && s.uwagi ? "uwagi" : "",
          (pole === "ulica" || pole === "ulica_droga") && s.ulica_zgodna === false ? "niezgodna" : ""].join(" ") });
        if ((pole === "ulica" || pole === "ulica_droga") && s.ulica_zgodna === false) {
          td.title = "Ulica z adresu różni się od drogi, przy której stoi słup";
        }
        if (edyt) przygotujEdycje(td, s, pole);
        tr.append(td);
      }
      tr.addEventListener("click", () => zaznacz(s.id, { centruj: true, zWykazu: true }));
      cialo.append(tr);
    }
    t.replaceChildren(glowa, cialo);
  }
  function przygotujEdycje(td, s, pole) {
    td.contentEditable = "plaintext-only";
    td.spellcheck = false;
    td.title = td.title || "Kliknij, aby poprawić – zmiana jest zapamiętywana w pliku projektu";
    let przed = "";
    td.addEventListener("focus", () => { przed = td.textContent; });
    td.addEventListener("click", (e) => e.stopPropagation());
    td.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); td.blur(); }
      if (e.key === "Escape") { td.textContent = przed; td.blur(); }
    });
    td.addEventListener("blur", () => {
      const nowa = td.textContent.trim();
      if (nowa !== przed.trim()) zmien("ustaw_pole", { id: s.id, atr: pole, wartosc: nowa });
    });
  }
  function renderArkusze() {
    const l = $("#lista-arkuszy");
    if (!S.dane) { l.replaceChildren(); return; }
    l.replaceChildren(...S.dane.arkusze.map((a) => el("button", {
      onclick: () => S.mapa && S.mapa.getView().fit([a.x0, a.y0, a.x0 + a.szer, a.y0 + a.wys], { padding: [60, 40, 40, 40], duration: 250 }),
    }, el("b", { text: `Arkusz ${a.nazwa}` }), el("span", { text: a.miejscowosci.join(", ") || "–" }))));
  }

  // ------------------------------------------------------------------ mapa
  const style = new Map();
  function styl(klucz, tworz) {
    if (!style.has(klucz)) style.set(klucz, tworz());
    return style.get(klucz);
  }
  function stylSlupa(f, res) {
    const s = slup(f.get("id"));
    if (!s) return null;
    const zazn = s.id === S.zazn, wyl = s.wykluczony;
    const etyk = S.warstwy.etykietyWidoczne && (res < 2.5 || zazn);
    const k = `${zazn}|${wyl}|${etyk ? s.etykieta : ""}`;
    return styl(k, () => {
      const kol = zazn ? kolor("--zazn") : wyl ? kolor("--slup-wyl") : kolor("--slup");
      const st = [new ol.style.Style({
        image: new ol.style.Circle({
          radius: zazn ? 7 : 4.5,
          fill: new ol.style.Fill({ color: wyl ? kolor("--powierzchnia") : kol }),
          stroke: new ol.style.Stroke({ color: wyl ? kol : kolor("--halo"), width: wyl ? 2 : 1.5 }),
        }),
        zIndex: zazn ? 3 : wyl ? 1 : 2,
      })];
      if (wyl) st.push(new ol.style.Style({ image: new ol.style.RegularShape({
        points: 4, radius: 6, radius2: 0, angle: Math.PI / 4, stroke: new ol.style.Stroke({ color: kolor("--blad"), width: 1.6 }) }) }));
      if (etyk && s.etykieta) st.push(new ol.style.Style({ text: new ol.style.Text({
        text: s.etykieta, offsetX: 9, offsetY: -8, textAlign: "left", font: `600 ${zazn ? 14 : 12}px Segoe UI, sans-serif`,
        fill: new ol.style.Fill({ color: kol }), stroke: new ol.style.Stroke({ color: kolor("--halo"), width: 3 }) }), zIndex: 4 }));
      return st;
    });
  }
  function warstwaWektorowa(stylFn, z) {
    return new ol.layer.Vector({ source: new ol.source.Vector(), style: stylFn, zIndex: z, updateWhileInteracting: true });
  }
  function wms(klucz) {
    const [url, warstwy, przezr, atr] = WMS[klucz];
    return new ol.layer.Image({
      visible: false, zIndex: przezr ? 1 : 0, maxResolution: przezr ? 4 : undefined,
      source: new ol.source.ImageWMS({
        url, ratio: 1.2, attributions: atr,
        params: { LAYERS: warstwy, STYLES: warstwy.split(",").map(() => "").join(","), VERSION: "1.1.1",
                  FORMAT: przezr ? "image/png" : "image/jpeg", TRANSPARENT: przezr },
      }),
    });
  }
  function przygotujMape(d) {
    let kod = d.epsg ? `EPSG:${d.epsg}` : "WT:lokalny";
    if (d.epsg && !ol.proj.get(kod)) {
      proj4.defs(kod, d.proj4);
      ol.proj.proj4.register(proj4);
      if (d.zakres_ukladu) ol.proj.get(kod).setExtent(d.zakres_ukladu);
    } else if (!d.epsg && !ol.proj.get(kod)) {
      ol.proj.addProjection(new ol.proj.Projection({ code: kod, units: "m" }));
    }
    if (S.mapa && S.kod === kod) return;
    S.kod = kod;
    const widok = new ol.View({ projection: kod, maxZoom: 28, constrainResolution: false });
    if (S.mapa) { S.mapa.setView(widok); ustawTlo(); return; }

    const W = S.warstwy;
    W.osm = new ol.layer.Tile({ source: new ol.source.OSM(), visible: false, zIndex: 0 });
    for (const k of Object.keys(WMS)) W[k] = wms(k);
    W.strefy = warstwaWektorowa((f, res) => styl(`strefa|${res < 6 ? f.get("nazwa") : ""}`, () => new ol.style.Style({
      fill: new ol.style.Fill({ color: kolor("--strefa") + "14" }),
      stroke: new ol.style.Stroke({ color: kolor("--strefa"), width: 1.2, lineDash: [6, 4] }),
      text: res < 6 ? new ol.style.Text({ text: f.get("nazwa"), font: "600 12px Segoe UI, sans-serif", overflow: true,
        fill: new ol.style.Fill({ color: kolor("--strefa") }), stroke: new ol.style.Stroke({ color: kolor("--halo"), width: 3 }) }) : undefined,
    })), 5);
    W.arkusze = warstwaWektorowa((f, res) => {
      const rog = f.get("rog");
      return styl(`ark|${rog}|${rog ? "" : f.get("nazwa")}|${res < 12}`, () => rog
        ? new ol.style.Style({ fill: new ol.style.Fill({ color: kolor("--arkusz") + "1f" }) })
        : new ol.style.Style({
          stroke: new ol.style.Stroke({ color: kolor("--arkusz"), width: 1.5 }),
          text: new ol.style.Text({ text: f.get("nazwa"), font: `700 ${res < 12 ? 22 : 14}px Segoe UI, sans-serif`,
            fill: new ol.style.Fill({ color: kolor("--arkusz") + "cc" }), stroke: new ol.style.Stroke({ color: kolor("--halo"), width: 3 }) }),
        }));
    }, 6);
    W.trasa = warstwaWektorowa(() => styl("trasa", () => new ol.style.Style({
      stroke: new ol.style.Stroke({ color: kolor("--trasa"), width: 2 }) })), 7);
    W.wyrozn = warstwaWektorowa(() => styl("wyrozn", () => new ol.style.Style({
      stroke: new ol.style.Stroke({ color: kolor("--zazn"), width: 6 }) })), 8);
    W.slupy = warstwaWektorowa(stylSlupa, 9);
    W.slupy.setProperties({ declutter: false });

    S.mapa = new ol.Map({
      target: "mapa", view: widok,
      layers: [W.osm, W.orto, W.topo, W.egib, W.gesut, W.strefy, W.arkusze, W.trasa, W.wyrozn, W.slupy],
      interactions: ol.interaction.defaults.defaults({ doubleClickZoom: false }),
      controls: ol.control.defaults.defaults({ rotate: false, attributionOptions: { collapsible: true } })
        .extend([new ol.control.ScaleLine()]),
    });
    S.mapa.on("singleclick", (e) => {
      const f = S.mapa.forEachFeatureAtPixel(e.pixel, (x) => x, { layerFilter: (l) => l === W.slupy, hitTolerance: 6 });
      if (f) zaznacz(f.get("id"), { przewinWykaz: true });
      else { S.zazn = null; W.wyrozn.getSource().clear(); odswiezZaznaczenie(); }
    });
    S.mapa.on("dblclick", (e) => {
      const f = S.mapa.forEachFeatureAtPixel(e.pixel, (x) => x, { layerFilter: (l) => l === W.slupy, hitTolerance: 6 });
      if (f) { S.zazn = f.get("id"); zmien("przelacz_wykluczenie", { id: f.get("id") }); }
    });
    S.mapa.on("pointermove", (e) => {
      if (e.dragging) return;
      const trafiony = S.mapa.hasFeatureAtPixel(e.pixel, { layerFilter: (l) => l === W.slupy, hitTolerance: 6 });
      S.mapa.getTargetElement().style.cursor = trafiony ? "pointer" : "";
    });
    const NAZWY = { osm: "OpenStreetMap", orto: "Ortofotomapa", topo: "Mapa topograficzna", egib: "EGiB", gesut: "GESUT" };
    for (const k of Object.keys(NAZWY)) sledzLadowanie(W[k].getSource(), NAZWY[k]);
    ustawTlo();
    ustawNakladki();
  }
  // wskaźnik ładowania podkładów i komunikat, gdy usługa nie odpowiada
  const ladowanie = { trwa: 0, bledy: new Set() };
  function pokazLadowanie() {
    const e = $("#ladowanie");
    const b = [...ladowanie.bledy];
    e.classList.toggle("blad", !!b.length);
    e.textContent = b.length ? `Nie udało się pobrać: ${b.join(", ")} (sprawdź internet)` : "Ładowanie podkładu…";
    e.classList.toggle("ukryte", !ladowanie.trwa && !b.length);
  }
  // Usługi GUGiK chwilowo odrzucają część żądań (przy kolejnej próbie działają) - obraz WMS,
  // który się nie wczytał, jest pobierany ponownie (do 2 razy), zanim zgłosimy błąd.
  function sledzLadowanie(zrodlo, nazwa) {
    let ponowienia = 0, ponawiam = false;
    const start = () => {
      if (!ponawiam) ponowienia = 0;  // nowy widok mapy - pełna pula ponowień
      ponawiam = false;
      ladowanie.trwa++;
      pokazLadowanie();
    };
    const koniec = (blad) => () => {
      ladowanie.trwa = Math.max(0, ladowanie.trwa - 1);
      if (!blad) ladowanie.bledy.delete(nazwa);
      else if (zrodlo instanceof ol.source.ImageWMS && ponowienia < 2) {
        ponowienia++;
        setTimeout(() => { ponawiam = true; zrodlo.refresh(); }, 800 * ponowienia);
      } else ladowanie.bledy.add(nazwa);
      pokazLadowanie();
    };
    for (const typ of ["imageloadstart", "tileloadstart"]) zrodlo.on(typ, start);
    for (const typ of ["imageloadend", "tileloadend"]) zrodlo.on(typ, koniec(false));
    for (const typ of ["imageloaderror", "tileloaderror"]) zrodlo.on(typ, koniec(true));
  }
  function renderMapa(dopasuj) {
    const d = S.dane;
    if (!d) return;
    przygotujMape(d);
    const W = S.warstwy;
    W.slupy.getSource().clear();
    W.slupy.getSource().addFeatures(d.slupy.map((s) => new ol.Feature({ geometry: new ol.geom.Point([s.x, s.y]), id: s.id })));
    W.trasa.getSource().clear();
    W.trasa.getSource().addFeatures(d.krawedzie.map(([a, b]) => new ol.Feature({
      geometry: new ol.geom.LineString([[d.slupy[a].x, d.slupy[a].y], [d.slupy[b].x, d.slupy[b].y]]) })));
    W.arkusze.getSource().clear();
    const [zx0, , , zy1] = d.zakazane;
    W.arkusze.getSource().addFeatures(d.arkusze.flatMap((a) => [
      new ol.Feature({ geometry: ol.geom.Polygon.fromExtent([a.x0, a.y0, a.x0 + a.szer, a.y0 + a.wys]), nazwa: a.nazwa }),
      new ol.Feature({ geometry: ol.geom.Polygon.fromExtent([a.x0 + zx0, a.y0, a.x0 + a.szer, a.y0 + zy1]), rog: true }),
    ]));
    W.strefy.getSource().clear();
    W.strefy.getSource().addFeatures(d.stacje.flatMap((s) => s.obrysy.map((o) =>
      new ol.Feature({ geometry: new ol.geom.Polygon([o]), nazwa: s.nazwa }))));
    if (dopasuj) dopasujWidok();
  }
  function dopasujWidok() {
    if (!S.mapa || !S.dane) return;
    const e = S.warstwy.slupy.getSource().getExtent();
    if (!ol.extent.isEmpty(e)) S.mapa.getView().fit(ol.extent.buffer(e, 20), { padding: [60, 50, 40, 50], minResolution: 0.15 });
  }
  function ustawTlo() {
    const tlo = pamiec.czytaj("tlo", "osm");
    $$('input[name="tlo"]').forEach((r) => { r.checked = r.value === tlo; });
    const lokalny = S.kod === "WT:lokalny";
    for (const k of ["osm", "orto", "topo"]) if (S.warstwy[k]) S.warstwy[k].setVisible(!lokalny && tlo === k);
  }
  function ustawNakladki() {
    const n = pamiec.czytaj("nakladki", { strefy: true, arkusze: true, etykiety: true });
    $$("[data-warstwa]").forEach((c) => { c.checked = !!n[c.dataset.warstwa]; });
    const W = S.warstwy;
    if (!W.slupy) return;
    const lokalny = S.kod === "WT:lokalny";
    W.egib.setVisible(!lokalny && !!n.egib);
    W.gesut.setVisible(!lokalny && !!n.gesut);
    W.strefy.setVisible(!!n.strefy);
    W.arkusze.setVisible(!!n.arkusze);
    W.etykietyWidoczne = !!n.etykiety;
    style.clear();
    W.slupy.changed();
  }

  // ------------------------------------------------------------------ zaznaczanie
  function zaznacz(id, { centruj = false, przewinWykaz = false } = {}) {
    S.zazn = id;
    S.warstwy.wyrozn && S.warstwy.wyrozn.getSource().clear();
    const s = slup(id);
    if (s && centruj && S.mapa) {
      const v = S.mapa.getView();
      const widoczny = ol.extent.containsCoordinate(v.calculateExtent(S.mapa.getSize()), [s.x, s.y]);
      if (!widoczny || v.getResolution() > 2) v.animate({ center: [s.x, s.y], resolution: Math.min(v.getResolution(), 0.8), duration: 250 });
    }
    odswiezZaznaczenie(przewinWykaz);
  }
  function pokazSlupy(ids, odcinek) {
    if (!S.mapa || !ids.length) return;
    const pkt = ids.map(slup).filter(Boolean);
    zaznacz(pkt[0].id, { przewinWykaz: true });
    if (odcinek && odcinek.length === 2) {
      const [a, b] = odcinek.map(slup);
      S.warstwy.wyrozn.getSource().addFeature(new ol.Feature({ geometry: new ol.geom.LineString([[a.x, a.y], [b.x, b.y]]) }));
    }
    const e = ol.extent.boundingExtent(pkt.map((s) => [s.x, s.y]));
    S.mapa.getView().fit(ol.extent.buffer(e, 25), { padding: [80, 60, 120, 60], maxZoom: 22, minResolution: 0.25, duration: 300 });
  }
  function odswiezZaznaczenie(przewinWykaz = false) {
    style.clear();
    S.warstwy.slupy && S.warstwy.slupy.changed();
    $$("#wykaz tr.zaznaczony").forEach((tr) => tr.classList.remove("zaznaczony"));
    const tr = S.zazn != null ? $(`#wykaz tr[data-id="${S.zazn}"]`) : null;
    if (tr) {
      tr.classList.add("zaznaczony");
      if (przewinWykaz) tr.scrollIntoView({ block: "nearest" });
    }
    odswiezKarte();
  }
  function odswiezKarte() {
    const k = $("#karta-slupa"), s = S.zazn != null ? slup(S.zazn) : null;
    if (!s) { k.classList.add("ukryte"); return; }
    k.classList.remove("ukryte");
    const opis = [s.stacja && `stacja ${s.stacja}`, s.id_slupa && `nr ${s.id_slupa}`,
                  [s.rodzaj_slupa, s.typ_slupa].filter(Boolean).join(" "), s.dzialka && `dz. ${s.dzialka}`].filter(Boolean);
    k.replaceChildren(...[
      el("div", { class: "tytul" }, s.wykluczony ? "Słup wyłączony z numeracji" : `Słup ${s.etykieta}`,
         el("span", { class: "szczegoly", text: opis.join(" · ") })),
      el("div", { class: "szczegoly", text: s.adres || "brak adresu" }),
      s.uwagi ? el("div", { class: "szczegoly", text: s.uwagi }) : null,
      el("div", { class: "rzad" },
         el("button", { disabled: !!S.praca, text: s.wykluczony ? "Włącz do numeracji" : "Wyłącz z numeracji",
                        onclick: () => zmien("przelacz_wykluczenie", { id: s.id }) }),
         el("button", { text: "Pokaż w wykazie", onclick: () => { pokazZakladke("wykaz"); odswiezZaznaczenie(true); } }),
         el("button", { class: "ikona", text: "×", title: "Zamknij", "aria-label": "Zamknij",
                        onclick: () => { S.zazn = null; odswiezZaznaczenie(); } }))].filter(Boolean));
  }
  function szukaj() {
    const q = $("#szukaj").value.trim().toLowerCase();
    if (!q || !S.dane) return;
    const s = S.dane.slupy.find((x) => (x.etykieta || "").toLowerCase() === q) ||
              S.dane.slupy.find((x) => (x.id_slupa || "").toLowerCase() === q || (x.nr_w_sieci || "").toLowerCase() === q) ||
              S.dane.slupy.find((x) => (x.id_slupa || "").toLowerCase().includes(q));
    if (s) pokazSlupy([s.id]); else status(`Nie znaleziono słupa „${$("#szukaj").value.trim()}”.`);
  }

  // ------------------------------------------------------------------ okna dialogowe
  function okno(tresc, przyciski, { szerokie = false } = {}) {
    return new Promise((zakoncz) => {
      const tlo = $("#okno"), o = $("#okno-tresc");
      const zamknij = (v) => { tlo.classList.add("ukryte"); document.removeEventListener("keydown", klawisz); zakoncz(v); };
      const klawisz = (e) => { if (e.key === "Escape") zamknij(null); };
      o.style.width = szerokie ? "min(760px, 94vw)" : "";
      o.replaceChildren(...tresc.filter(Boolean), el("div", { class: "stopka" }, przyciski.map((p) => el("button", {
        class: p.glowny ? "glowny" : "", text: p.tekst,
        onclick: async () => { const v = p.wartosc ? await p.wartosc() : p.zwroc; if (v !== undefined) zamknij(v); },
      }))));
      tlo.classList.remove("ukryte");
      document.addEventListener("keydown", klawisz);
      const g = o.querySelector("button.glowny") || o.querySelector(".stopka button");
      g && g.focus();
    });
  }
  const komunikat = (tytul, tekst) => okno([el("h3", { text: tytul }), el("p", { text: tekst })],
                                           [{ tekst: "OK", zwroc: true, glowny: true }]);

  async function oknoPotwierdzenia(s) {
    const tresc = [el("h3", { text: "Czy wykonać numerację?" }), el("div", { text: "Plan numeracji:" }),
      el("ul", {}, s.plan.map((x) => el("li", { text: x })))];
    if (s.istniejaca) tresc.push(el("p", { text: `Na warstwie ${s.warstwa} jest już ${s.istniejaca} numerów – zostaną zastąpione.` }));
    if (s.bledne_kliki) tresc.push(el("p", { text: `Scalono ${s.bledne_kliki} błędnych klików.` }));
    if (s.arkusze) tresc.push(el("p", { text: `Arkusze 1:1000: ${s.arkusze} (układy papieru 1–${s.arkusze}).` }));
    tresc.push(el("p", {}, "Pliki zostaną zapisane w: ", el("b", { text: s.katalog })));
    let wgs = null;
    if (s.pytaj_o_uklad) {
      wgs = el("input", { type: "radio", name: "uklad", value: "wgs" });
      tresc.push(el("div", { class: "wybor" }, el("b", { text: "Współrzędne słupów w piśmie i zestawieniach" }),
        el("label", { class: "check" }, el("input", { type: "radio", name: "uklad", value: "2000", checked: true }), "PL-2000 (układ projektu)"),
        el("label", { class: "check" }, wgs, "WGS 84 (szerokość, długość)"),
        s.projektowa ? el("span", { class: "info", text: "Tabela projektowa zawsze ma współrzędne GPS (WGS 84)." }) : null));
    }
    return okno(tresc, [{ tekst: "Anuluj", zwroc: null },
                        { tekst: "Numeruj i zapisz", glowny: true, wartosc: () => ({ wgs84: !!(wgs && wgs.checked) }) }],
                { szerokie: true });
  }
  const generuj = bezpiecznie(async () => {
    if (S.praca || !S.dane) return;
    const o = opcje();
    const s = await rpc("podsumowanie_generowania", { opcje: o });
    if (s.ponowna_analiza) {
      await komunikat("Zmieniono scalanie wierzchołków", "Projekt zostanie przeanalizowany ponownie. Po analizie kliknij jeszcze raz „Numeruj i generuj”.");
      await analizuj();
      return;
    }
    const w = await oknoPotwierdzenia(s);
    if (!w) { log("Przerwano – nic nie zapisano."); return; }
    pamiec.zapisz("wyniki", o.wyniki);
    await rpc("generuj", { opcje: { ...o, wgs84: w.wgs84 } });
    ustawPrace("generuj");
  });
  async function oknoWynikow(w) {
    const tresc = [el("h3", { text: w.bledy.length ? "Gotowe z błędami" : "Gotowe" }),
      el("div", { text: "Zapisano:" }), el("ul", {}, w.zapisane.map((x) => el("li", { text: x })))];
    if (w.bledy.length) tresc.push(el("div", { class: "blad-tekst", text: "Błędy:" }),
                                   el("ul", { class: "blad-tekst" }, w.bledy.map((x) => el("li", { text: x }))));
    const v = await okno(tresc, [{ tekst: "Otwórz folder", zwroc: "folder" }, { tekst: "Zamknij", zwroc: null, glowny: true }]);
    if (v === "folder") bezpiecznie(() => rpc("otworz_folder", { katalog: w.katalog }))();
  }
  async function oknoOperatora() {
    const pola = {};
    const nip = el("input", { type: "text", placeholder: "822-234-93-74" });
    const klucz = el("input", { type: "text", value: (S.start.ustawienia || {}).klucz_gus || "",
                                placeholder: "bez klucza dane pochodzą z białej listy MF" });
    const info = el("div", { class: "info", text: "Dane adresowe: GUS (gdy podasz klucz) albo biała lista MF; numer RPT: rejestr UKE." });
    const blad = el("div", { class: "blad-tekst" });
    const pobierz = el("button", { class: "glowny", text: "Pobierz z rejestrów", onclick: async () => {
      blad.textContent = ""; pobierz.disabled = true; pobierz.textContent = "Pobieranie…";
      try {
        const r = await rpc("operator_po_nip", { nip: nip.value, klucz_gus: klucz.value.trim() });
        for (const k of POLA_OPERATORA) {
          pola[k].value = r.wpis[k] || "";
          pola[k].classList.toggle("zmienione", k in r.bylo);
          pola[k].title = k in r.bylo ? `Było: ${r.bylo[k] || "–"}` : "";
        }
        info.replaceChildren(...r.info.flatMap((t) => [t, el("br")]));
      } catch (e) { blad.textContent = e.message; }
      pobierz.disabled = false; pobierz.textContent = "Pobierz z rejestrów";
    } });
    nip.addEventListener("keydown", (e) => { if (e.key === "Enter") pobierz.click(); });
    const form = el("div", { class: "formularz" }, POLA_OPERATORA.flatMap((k) => {
      pola[k] = el("input", { type: "text", placeholder: k === "Nazwa" ? "krótka nazwa na liście wyboru" : "" });
      return [el("label", { text: k }), pola[k]];
    }));
    const wynik = await okno([
      el("h3", { text: "Dodaj operatora po NIP" }), el("div", { class: "rzad" }, nip, pobierz), info,
      form, el("div", { class: "formularz" }, el("label", { text: "Klucz GUS (opcjonalnie)" }), klucz), blad,
    ], [{ tekst: "Anuluj", zwroc: null }, { tekst: "Zapisz na liście", glowny: true, wartosc: async () => {
      try {
        const wpis = Object.fromEntries(POLA_OPERATORA.map((k) => [k, pola[k].value]));
        return await rpc("zapisz_operatora", { wpis });
      } catch (e) { blad.textContent = e.message; return undefined; }
    } }], { szerokie: true });
    if (wynik) { wypelnijListy(wynik, wynik.operator, null); renderKroki(); }
  }

  // ------------------------------------------------------------------ zakładki, motyw, kroki
  function pokazZakladke(nazwa) {
    $$(".zakladka").forEach((z) => z.classList.toggle("aktywna", z.dataset.zakladka === nazwa));
    $$(".tresc").forEach((t) => t.classList.toggle("ukryte", t.dataset.tresc !== nazwa));
    $("#filtr").classList.toggle("ukryte", nazwa !== "wykaz");
    $("#dolny").classList.remove("zwiniety");
    S.mapa && setTimeout(() => S.mapa.updateSize(), 0);
  }
  function ustawMotyw(m) {
    document.documentElement.dataset.motyw = m;
    style.clear();
    if (S.warstwy.slupy) for (const k of ["slupy", "trasa", "arkusze", "strefy", "wyrozn"]) S.warstwy[k].changed();
  }
  function sprawdzTolerancje() {
    const d = S.dane;
    const rozne = d && Math.abs((parseFloat($("#tolerancja").value) || 0) - d.podsumowanie.tolerancja_analizy) > 1e-9;
    $("#uwaga-tolerancja").classList.toggle("ukryte", !rozne);
  }
  function przejdzDoKroku(k) {
    const cel = { projekt: "#s-projekt", zlecenie: "#s-zlecenie", wyniki: "#s-wyniki", kontrola: "#prawy" }[k];
    const e = $(cel);
    e.scrollIntoView({ behavior: "smooth", block: "start" });
    const karta = k === "kontrola" ? $(".sekcja") : e;
    if (karta) { karta.classList.add("podswietlona"); setTimeout(() => karta.classList.remove("podswietlona"), 1200); }
  }

  // ------------------------------------------------------------------ start
  function podlacz() {
    $("#analizuj").addEventListener("click", analizuj);
    $("#wybierz-plik").addEventListener("click", wybierzPlik);
    $("#plik").addEventListener("keydown", (e) => { if (e.key === "Enter") analizuj(); });
    $("#generuj").addEventListener("click", generuj);
    $("#otworz-folder").addEventListener("click", bezpiecznie(() => rpc("otworz_folder", { katalog: $("#katalog").value.trim() })));
    $("#wybierz-katalog").addEventListener("click", bezpiecznie(async () => {
      const r = await rpc("wybierz_katalog", { start: $("#katalog").value.trim() });
      if (r.brak_dialogu) { $("#katalog").focus(); status("Wpisz ścieżkę folderu wyników."); }
      else if (r.katalog) $("#katalog").value = r.katalog;
    }));
    $("#edytuj-listy").addEventListener("click", bezpiecznie(() => rpc("edytuj_listy")));
    $("#odswiez-listy").addEventListener("click", bezpiecznie(async () => {
      wypelnijListy(await rpc("odswiez_slowniki")); log("Odświeżono listy operatorów i rejonów.");
    }));
    $("#dodaj-operatora").addEventListener("click", oknoOperatora);
    for (const id of ["#prefiks", "#numer-startowy", "#kierunek", "#rejon"]) $(id).addEventListener("change", przelicz);
    $("#operator").addEventListener("change", () => { renderKroki(); rpc("zapisz_ustawienia_okna", { ustawienia: { operator: $("#operator").value } }).catch(() => {}); });
    $("#zakladka").addEventListener("input", przeliczArkusze);
    $("#tolerancja").addEventListener("input", sprawdzTolerancje);
    $$("[data-wynik]").forEach((c) => c.addEventListener("change", () => { zaleznosciWynikow(); pamiec.zapisz("wyniki", wyniki()); }));
    $("#przyjmij-ulice").addEventListener("click", async () => {
      const u = S.dane.kontrola.find((s) => s.id === "ulice");
      const ok = await okno([el("h3", { text: `Zmienić ulicę dla ${u.pozycje.length} słupów?` }),
        el("ul", {}, u.pozycje.slice(0, 25).map((p) => el("li", { text: `${p.tytul}: ${p.szczegoly}` }))),
        u.pozycje.length > 25 ? el("p", { text: "…" }) : null],
        [{ tekst: "Anuluj", zwroc: null }, { tekst: "Przyjmij ulice z dróg", glowny: true, zwroc: true }]);
      if (ok) zmien("przyjmij_ulice", {});
    });
    $("#szukaj").addEventListener("keydown", (e) => { if (e.key === "Enter") szukaj(); });
    $("#dopasuj").addEventListener("click", dopasujWidok);
    $("#warstwy-przycisk").addEventListener("click", (e) => {
      e.stopPropagation();
      const m = $("#warstwy-menu");
      m.classList.toggle("ukryte");
      $("#warstwy-przycisk").setAttribute("aria-expanded", String(!m.classList.contains("ukryte")));
    });
    document.addEventListener("click", (e) => { if (!e.target.closest(".rozwijane")) $("#warstwy-menu").classList.add("ukryte"); });
    $$('input[name="tlo"]').forEach((r) => r.addEventListener("change", () => { pamiec.zapisz("tlo", r.value); ustawTlo(); }));
    $$("[data-warstwa]").forEach((c) => c.addEventListener("change", () => {
      pamiec.zapisz("nakladki", Object.fromEntries($$("[data-warstwa]").map((x) => [x.dataset.warstwa, x.checked])));
      ustawNakladki();
    }));
    $$(".zakladka").forEach((z) => z.addEventListener("click", () => pokazZakladke(z.dataset.zakladka)));
    $("#filtr").addEventListener("input", odczekaj(() => { renderWykaz(); odswiezZaznaczenie(); }, 200));
    $("#zwin").addEventListener("click", () => {
      const d = $("#dolny");
      d.classList.toggle("zwiniety");
      $("#zwin").textContent = d.classList.contains("zwiniety") ? "▴" : "▾";
      S.mapa && setTimeout(() => S.mapa.updateSize(), 0);
    });
    $$(".krok").forEach((b) => b.addEventListener("click", () => przejdzDoKroku(b.dataset.krok)));
    $("#motyw").addEventListener("click", () => {
      const m = document.documentElement.dataset.motyw === "ciemny" ? "jasny" : "ciemny";
      pamiec.zapisz("motyw", m);
      ustawMotyw(m);
    });
    window.addEventListener("beforeunload", (e) => { if (S.praca) { e.preventDefault(); e.returnValue = ""; } });
  }

  async function start() {
    ustawMotyw(pamiec.czytaj("motyw", matchMedia("(prefers-color-scheme: dark)").matches ? "ciemny" : "jasny"));
    podlacz();
    try {
      S.start = await rpc("start");
    } catch (e) {
      status(e.message);
      setTimeout(start, 1500);
      return;
    }
    const st = S.start, u = st.ustawienia || {};
    S.dialogi = st.dialogi;
    // po przeładowaniu strony: historia dziennika, ale bez ponownej obsługi zakończonych prac
    S.nrZd = st.nr_zdarzenia;
    $("#dziennik").textContent = st.dziennik.length ? st.dziennik.join("\n") + "\n" : "";
    wypelnijListy(st.slowniki, u.operator, u.rejon);
    $("#plik").value = st.ostatni_plik || "";
    $("#opracowal").value = u.opracowal || "";
    $("#umowa-od").value = dataISO(st.dzis);
    $("#data-rysunku").value = st.miesiac;
    $("#tolerancja").value = st.domyslne.tolerancja_slupa;
    $("#zakladka").value = st.domyslne.zakladka;
    const w = u.wyniki || pamiec.czytaj("wyniki", null);
    if (w) $$("[data-wynik]").forEach((c) => { if (c.dataset.wynik in w) c.checked = !!w[c.dataset.wynik]; });
    if (!S.dialogi) $("#wybierz-plik").title = "W przeglądarce wpisz ścieżkę pliku w polu obok";
    zaleznosciWynikow();
    ustawNakladki();
    if (st.projekt) { S.dane = st.projekt; S.plikUstawien = st.projekt.plik; renderuj(true); }
    else renderKroki();
    if (st.praca) ustawPrace(st.praca);
    petla();
  }
  start();
})();
