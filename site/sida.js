// Kropp64, kropp64.se. Små detaljer: POST-skärmen skrivs en gång, sensortabellen tickar med syntetiska
// värden, värmekameran, staplarna fylls när de syns, kontorsfilmen laddas först när den syns, flikens uptime.
(function () {
  var lugn = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  function lagra(k, v) { try { if (v === undefined) return sessionStorage.getItem(k); sessionStorage.setItem(k, v); } catch (e) { return null; } }

  // tema
  var temaKnapp = document.querySelector('.tema');
  if (temaKnapp) temaKnapp.addEventListener('click', function () {
    var r = document.documentElement;
    var mork = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    r.dataset.theme = mork ? 'light' : 'dark';
    try { localStorage.setItem('k64-tema', r.dataset.theme); } catch (e) {}
  });

  // POST-skärmen: skrivs ut rad för rad första gången under besöket
  var post = document.querySelector('.post');
  if (post && !lugn && !lagra('k64-post')) {
    lagra('k64-post', '1');
    var rader = [].slice.call(post.querySelectorAll('span'));
    var html = rader.map(function (r) { return r.innerHTML; });
    post.style.height = post.offsetHeight + 'px';
    rader.forEach(function (r) { r.innerHTML = ''; });
    post.classList.add('skriver');
    var i = 0;
    (function nasta() {
      if (i >= rader.length) { post.classList.remove('skriver'); post.style.height = ''; return; }
      var r = rader[i], full = html[i], text = full.replace(/<[^>]+>/g, ''), n = 0;
      var ok = /<b>/.test(full);
      var steg = ok ? text.indexOf('OK') : text.length;
      r.classList.add('markor');
      var t = setInterval(function () {
        n += 3;
        if (n >= steg) {
          clearInterval(t);
          r.textContent = text.slice(0, steg);
          setTimeout(function () { r.innerHTML = full; r.classList.remove('markor'); i++; nasta(); }, ok ? 140 : 0);
        } else r.textContent = text.slice(0, n);
      }, 16);
    })();
  }

  // sensortabellen: slumpvandring inom rimliga gränser, Min/Max/Medel följer med
  var fmt = function (v, d) { return v.toFixed(d).replace('.', ','); };
  var rader2 = [].slice.call(document.querySelectorAll('.sensorer tr[data-s]'));
  var tillstand = rader2.map(function (tr) {
    var c = tr.children;
    var tal = function (td) { return parseFloat(td.textContent.replace(/\s/g, '').replace(',', '.')); };
    return { tr: tr, v: +tr.dataset.v, lo: +tr.dataset.lo, hi: +tr.dataset.hi, d: +tr.dataset.d,
             min: tal(c[2]), max: tal(c[3]), medel: tal(c[4]), n: 40, enhet: c[1].querySelector('u').outerHTML };
  });
  var rrUt = document.querySelector('.rr-ut'), rotor = document.querySelector('.flakt-rotor');
  function tick() {
    var s = tillstand[Math.floor(Math.random() * tillstand.length)];
    var steg = (s.hi - s.lo) * 0.12, ny = s.v + (Math.random() - 0.5) * 2 * steg;
    ny = Math.max(s.lo, Math.min(s.hi, ny));
    var avr = Math.pow(10, s.d); ny = Math.round(ny * avr) / avr;
    if (ny === s.v) return;
    s.v = ny; s.n++;
    s.medel = s.medel + (ny - s.medel) / s.n;
    var c = s.tr.children;
    c[1].innerHTML = fmt(ny, s.d) + ' ' + s.enhet;
    c[1].classList.remove('lyft'); void c[1].offsetWidth; c[1].classList.add('lyft');
    if (ny < s.min) { s.min = ny; c[2].innerHTML = fmt(ny, s.d) + ' ' + s.enhet; }
    if (ny > s.max) { s.max = ny; c[3].innerHTML = fmt(ny, s.d) + ' ' + s.enhet; }
    c[4].innerHTML = fmt(s.medel, s.d) + ' ' + s.enhet;
    if (s.tr.dataset.s === 'rr' && rrUt) {
      rrUt.textContent = fmt(ny, 1);
      if (rotor) rotor.style.animationDuration = (60 / ny).toFixed(3) + 's';
    }
  }
  if (!lugn && tillstand.length) {
    var tabell = document.querySelector('.sensorer'), tid = null;
    new IntersectionObserver(function (e) {
      if (e[0].isIntersecting) { if (!tid) tid = setInterval(tick, 1100); }
      else { clearInterval(tid); tid = null; }
    }).observe(tabell);
  }

  // värmekameran
  var knapp = document.querySelector('.varmeknapp'), bild = document.querySelector('.bild');
  if (knapp && bild) knapp.addEventListener('click', function () {
    var varm = bild.querySelector('.varme');
    if (!varm.dataset.laddad) {
      varm.querySelectorAll('[data-srcset]').forEach(function (s) { s.srcset = s.dataset.srcset; });
      var im = varm.querySelector('img'); im.src = im.dataset.src; varm.dataset.laddad = '1';
    }
    var pa = bild.dataset.lage !== 'varme';
    bild.dataset.lage = pa ? 'varme' : 'foto';
    varm.hidden = !pa;
    knapp.setAttribute('aria-pressed', pa ? 'true' : 'false');
  });

  // staplarna fylls när testet syns, filmen laddas först när den syns
  var bench = document.querySelector('.bench');
  if (bench) new IntersectionObserver(function (e, o) {
    if (e[0].isIntersecting) { bench.classList.add('syns'); o.disconnect(); }
  }, { threshold: .25 }).observe(bench);
  var film = document.querySelector('.kontoret video');
  if (film) new IntersectionObserver(function (e) {
    if (e[0].isIntersecting) {
      if (!film.src) { film.src = film.dataset.src; film.preload = 'auto'; }
      if (!lugn) film.play().catch(function () {});
    } else if (film.src) film.pause();
  }, { rootMargin: '200px' }).observe(film);

  // uptime för fliken
  var up = document.querySelector('.uptime span'), start = Date.now();
  if (up) setInterval(function () {
    var s = Math.floor((Date.now() - start) / 1000), p = function (n) { return (n < 10 ? '0' : '') + n; };
    up.textContent = p(Math.floor(s / 3600)) + ':' + p(Math.floor(s / 60) % 60) + ':' + p(s % 60);
  }, 1000);
})();
