/**
 * guia.js — Personaje guía y sistema de tutorial paso a paso
 * Atril de San Juan — A.M. Stmo. Cristo de la Salud — Alcalá la Real
 */

'use strict';

// ============================================================
// Precargar imágenes de poses para evitar parpadeos
// ============================================================
const _NOMBRES_POSES = [
    'reposo', 'parpadeo', 'saludo_mano', 'saludo_visera',
    'senala_izquierda', 'senala_derecha', 'senala_arriba', 'senala_abajo',
    'celebra', 'pulgar', 'pensando', 'partitura',
];

const _imgsPoses = {};
_NOMBRES_POSES.forEach(nombre => {
    const img = new Image();
    img.src = 'img/guia/' + nombre + '.png';
    _imgsPoses[nombre] = img;
});

// ============================================================
// Referencias a elementos del DOM (creados en _crearElementosDOM)
// ============================================================
let _elGuia     = null;   // <button> del personaje
let _elGuiaImg  = null;   // <img> dentro del personaje
let _elOverlay  = null;   // overlay semi-transparente
let _elFoco     = null;   // caja del spotlight
let _elBurbuja  = null;   // burbuja de texto

// ============================================================
// Estado interno del módulo
// ============================================================
let _pasos          = {};     // pasos cargados de tutorial.json  {pantalla: [...]}
let _prefs          = { tutoriales_vistos: [] };
let _cargado        = false;   // pasos y preferencias ya cargados
let _rafFoco        = 0;       // bucle que mantiene el foco sobre su elemento
let _ultimoRectFoco = '';
let _timerTransicionFoco = 0;
let _pantallActual  = 'inicio';
let _tourActivo     = false;
let _tourPantalla   = null;
let _tourPasosArr   = [];     // pasos filtrados del tour en curso
let _tourIdx        = 0;
let _timerParpadeo  = null;
let _poseActual     = 'reposo';
let _resizeTimer    = null;

// Pose de reposo según pantalla (se aplica cuando no hay tour activo)
const _POSE_PANTALLA = {
    inicio: 'reposo',
    subir:  'reposo',
    revisar:'partitura',
    empalme:'reposo',
    listo:  'celebra',
};

// ============================================================
// Inicialización (espera a que el DOM esté listo)
// ============================================================
document.addEventListener('DOMContentLoaded', _inicializar);

async function _inicializar() {
    _crearElementosDOM();

    // Escuchar YA los cambios de pantalla: app.js anuncia el inicio al arrancar,
    // antes de que terminen de cargar los pasos y las preferencias.
    document.addEventListener('pantalla', e => {
        _pantallActual = e.detail;
        if (_cargado) _alCambiarPantalla(e.detail);
    });

    // Revisar se notifica cuando los nombres ya están dibujados
    document.addEventListener('revisarListo', () => {
        _pantallActual = 'revisar';
        if (_cargado) _alCambiarPantalla('revisar');
    });

    // Reposicionar foco en cambio de tamaño
    window.addEventListener('resize', () => {
        if (!_tourActivo) return;
        clearTimeout(_resizeTimer);
        _resizeTimer = setTimeout(_reposicionarFoco, 200);
    });

    // Cargar pasos del tutorial
    try {
        const r = await fetch('tutorial.json');
        if (r.ok) _pasos = await r.json();
    } catch (_) { /* sin tutorial.json, guía sin pasos */ }

    // Cargar preferencias del servidor
    await _cargarPreferencias();

    _cargado = true;
    _iniciarAnimacionReposo();

    // Atender la pantalla en la que ya estamos (anunciada mientras cargábamos o visible en el DOM)
    const actual = _pantallActual || _pantallaVisible();
    if (actual) {
        _pantallActual = actual;
        _alCambiarPantalla(actual);
    }
}

/** Nombre de la pantalla visible ahora mismo ('inicio', 'subir'…), o null. */
function _pantallaVisible() {
    const seccion = document.querySelector('[id^="paso-"].activo');
    return seccion ? seccion.id.replace('paso-', '') : null;
}

// ============================================================
// Creación de elementos del DOM
// ============================================================
function _crearElementosDOM() {
    // 1. Overlay (bloquea clics durante el tour)
    _elOverlay = document.createElement('div');
    _elOverlay.id = 'guia-overlay';
    _elOverlay.className = 'guia-overlay';
    document.body.appendChild(_elOverlay);

    // 2. Foco (spotlight)
    _elFoco = document.createElement('div');
    _elFoco.id = 'guia-foco';
    _elFoco.className = 'guia-foco';
    document.body.appendChild(_elFoco);

    // 3. Burbuja de texto
    _elBurbuja = document.createElement('div');
    _elBurbuja.id = 'guia-burbuja';
    _elBurbuja.className = 'guia-burbuja';
    _elBurbuja.setAttribute('role', 'dialog');
    _elBurbuja.setAttribute('aria-modal', 'true');
    _elBurbuja.setAttribute('aria-label', 'Ayuda del tutorial');
    _elBurbuja.innerHTML = `
        <div class="guia-burbuja-titulo" id="guia-titulo"></div>
        <div class="guia-burbuja-texto"  id="guia-texto"></div>
        <div class="guia-burbuja-meta"   id="guia-meta"></div>
        <div class="guia-reset-link" id="guia-reset-link" style="display:none">
            <button class="enlace-neutro" id="btn-guia-reiniciar"
                    style="font-size:0.75rem;opacity:0.7">
                Volver a ver todos los tutoriales
            </button>
        </div>
        <div class="guia-burbuja-btns">
            <button class="btn-secundario" id="guia-btn-anterior"
                    style="font-size:0.78rem;padding:0.35rem 0.7rem">Anterior</button>
            <button class="btn-primario" id="guia-btn-siguiente"
                    style="font-size:0.78rem;padding:0.35rem 0.7rem">Siguiente</button>
            <button class="enlace-neutro" id="guia-btn-saltar"
                    style="font-size:0.75rem;opacity:0.65;margin-left:auto">Saltar</button>
        </div>`;
    document.body.appendChild(_elBurbuja);

    // 4. Personaje guía
    _elGuia = document.createElement('button');
    _elGuia.id = 'guia-personaje';
    _elGuia.className = 'guia-personaje';
    _elGuia.type = 'button';
    _elGuia.setAttribute('aria-label', '¿Te ayudo?');
    _elGuia.title = '¿Te ayudo?';

    _elGuiaImg = document.createElement('img');
    _elGuiaImg.id = 'guia-img';
    _elGuiaImg.src = 'img/guia/reposo.png';
    _elGuiaImg.alt = '';
    _elGuiaImg.setAttribute('aria-hidden', 'true');
    _elGuiaImg.className = 'animando';
    _elGuia.appendChild(_elGuiaImg);
    document.body.appendChild(_elGuia);

    // Eventos de la burbuja
    document.getElementById('guia-btn-siguiente').addEventListener('click', e => {
        e.stopPropagation();
        _avanzarPaso();
    });
    document.getElementById('guia-btn-anterior').addEventListener('click', e => {
        e.stopPropagation();
        _retrocederPaso();
    });
    document.getElementById('guia-btn-saltar').addEventListener('click', e => {
        e.stopPropagation();
        _terminarTour(true);
    });
    document.getElementById('btn-guia-reiniciar').addEventListener('click', e => {
        e.stopPropagation();
        _reiniciarTutoriales();
    });

    // Clic en el personaje
    _elGuia.addEventListener('click', _alClickGuia);

    // Teclado global para el tour
    document.addEventListener('keydown', _teclaGlobal);
}

// ============================================================
// Animación de reposo (parpadeo periódico + breathing)
// ============================================================
function _iniciarAnimacionReposo() {
    _programarParpadeo();
}

function _programarParpadeo() {
    clearTimeout(_timerParpadeo);
    // Entre 3 y 6 segundos de espera
    const espera = 3000 + Math.random() * 3000;
    _timerParpadeo = setTimeout(_parpadear, espera);
}

function _parpadear() {
    if (_tourActivo) { _programarParpadeo(); return; }
    // Solo parpadea si la pose actual no está en curso de cambio
    const posBase = _poseActual;
    _elGuiaImg.src = _imgsPoses['parpadeo'].src;
    setTimeout(() => {
        _elGuiaImg.src = _imgsPoses[posBase] ? _imgsPoses[posBase].src : _imgsPoses['reposo'].src;
        _programarParpadeo();
    }, 150);
}

/** Cambia la pose del personaje. */
function _setPose(nombre) {
    if (!_NOMBRES_POSES.includes(nombre)) nombre = 'reposo';
    _poseActual = nombre;
    _elGuiaImg.src = _imgsPoses[nombre].src;
}

// ============================================================
// Cambio de pantalla
// ============================================================
function _alCambiarPantalla(pantalla) {
    // Aplicar pose de pantalla si no hay tour activo
    if (!_tourActivo) {
        const pose = _POSE_PANTALLA[pantalla] || 'reposo';
        _setPose(pose);
    }

    // Si el tutorial de esta pantalla no ha sido visto, iniciarlo tras un breve retardo
    if (_pasos[pantalla] && !_tourActivo) {
        const yaVisto = _prefs.tutoriales_vistos.includes(pantalla);
        if (!yaVisto) {
            setTimeout(() => {
                // Comprobar que seguimos en la misma pantalla
                if (_pantallActual === pantalla && !_tourActivo) {
                    iniciarTour(pantalla);
                }
            }, 600);
        }
    }
}

// ============================================================
// Tour — arrancar, avanzar, terminar
// ============================================================

/** Inicia el tour de la pantalla indicada. Si ya hay uno activo, lo detiene primero. */
function iniciarTour(pantalla) {
    if (_tourActivo) _terminarTour(false);

    const pasosBrutos = _pasos[pantalla];
    if (!pasosBrutos || pasosBrutos.length === 0) return;

    _tourActivo   = true;
    _tourPantalla = pantalla;
    _tourPasosArr = pasosBrutos;  // sin filtrar; el salto se hace en _mostrarPasoActual
    _tourIdx      = 0;

    // Elevar el personaje sobre el overlay
    _elGuia.classList.add('tour-activo');

    // Mostrar overlay (el foco añade el efecto oscuro con box-shadow)
    _elOverlay.style.display = 'block';

    _mostrarPasoActual();
    _seguirFoco();
}

/** Mantiene el foco pegado a su elemento mientras dura el tour (animaciones, scroll, zoom). */
function _seguirFoco() {
    cancelAnimationFrame(_rafFoco);
    const paso = () => {
        if (!_tourActivo) return;
        const el = _selectorFocoActual && document.querySelector(_selectorFocoActual);
        if (el && _elFoco.style.display !== 'none') {
            const r = el.getBoundingClientRect();
            const clave = [r.top, r.left, r.width, r.height].map(Math.round).join(',');
            if (clave !== _ultimoRectFoco) {
                _ultimoRectFoco = clave;
                _reposicionarFoco();
            }
        }
        _rafFoco = requestAnimationFrame(paso);
    };
    _rafFoco = requestAnimationFrame(paso);
}

function _avanzarPaso() {
    _tourIdx++;
    if (_tourIdx >= _tourPasosArr.length) {
        _terminarTour(true);
        return;
    }
    _mostrarPasoActual();
}

function _retrocederPaso() {
    if (_tourIdx <= 0) return;
    _tourIdx--;
    _mostrarPasoActual();
}

function _terminarTour(marcarComoVisto) {
    _tourActivo = false;
    cancelAnimationFrame(_rafFoco);
    _ultimoRectFoco = '';
    _elGuia.classList.remove('tour-activo');

    _elOverlay.style.display = 'none';
    _elFoco.style.display    = 'none';
    _elBurbuja.style.display = 'none';

    // Restaurar pose de pantalla
    const pose = _POSE_PANTALLA[_pantallActual] || 'reposo';
    _setPose(pose);

    if (marcarComoVisto && _tourPantalla) {
        _marcarVisto(_tourPantalla);
    }

    _tourPantalla = null;
}

// ============================================================
// Renderizar el paso actual
// ============================================================
function _mostrarPasoActual() {
    // Transición suave del foco solo durante el cambio de paso
    _elFoco.classList.add('con-transicion');
    clearTimeout(_timerTransicionFoco);
    _timerTransicionFoco = setTimeout(() => _elFoco.classList.remove('con-transicion'), 400);

    // Avanzar sobre pasos ocultos con skipIfHidden
    while (_tourIdx < _tourPasosArr.length) {
        const paso = _tourPasosArr[_tourIdx];
        if (paso.skipIfHidden && !_elementoVisible(paso.selector)) {
            _tourIdx++;
        } else {
            break;
        }
    }
    if (_tourIdx >= _tourPasosArr.length) {
        _terminarTour(true);
        return;
    }

    const paso = _tourPasosArr[_tourIdx];

    // Pose
    const pose = paso.pose || _calcularPoseDireccion(paso.selector);
    _setPose(pose);

    // Título y texto
    document.getElementById('guia-titulo').textContent = paso.titulo || '';
    document.getElementById('guia-texto').textContent  = paso.texto  || '';

    // Contador
    const visibles = _contarPasosVisibles();
    const idxVisible = _indiceVisible();
    document.getElementById('guia-meta').textContent =
        visibles > 1 ? `${idxVisible} / ${visibles}` : '';

    // Botón anterior
    const btnAnt = document.getElementById('guia-btn-anterior');
    btnAnt.disabled = (_tourIdx === 0 || idxVisible <= 1);

    // Botón siguiente (último paso → "¡Entendido!")
    const esUltimo = _esUltimoPasoVisible();
    const btnSig = document.getElementById('guia-btn-siguiente');
    btnSig.textContent = esUltimo ? '¡Entendido!' : 'Siguiente';

    // Enlace de reinicio (solo en el paso con resetLink)
    const resetLink = document.getElementById('guia-reset-link');
    resetLink.style.display = paso.resetLink ? '' : 'none';

    // Mostrar burbuja
    _elBurbuja.style.display = 'block';

    // Focus en Siguiente para accesibilidad
    setTimeout(() => {
        const btnSigEl = document.getElementById('guia-btn-siguiente');
        if (btnSigEl) btnSigEl.focus();
    }, 50);

    // Spotlight (scrollIntoView + posición del foco)
    _iluminarElemento(paso.selector);
}

/** Cuenta cuántos pasos serán visibles (no skipIfHidden con elemento oculto). */
function _contarPasosVisibles() {
    return _tourPasosArr.filter((p, i) => {
        if (!p.skipIfHidden) return true;
        return _elementoVisible(p.selector);
    }).length;
}

/** Número de orden (1-based) del paso actual entre los visibles. */
function _indiceVisible() {
    let cuenta = 0;
    for (let i = 0; i <= _tourIdx; i++) {
        const p = _tourPasosArr[i];
        if (!p.skipIfHidden || _elementoVisible(p.selector)) cuenta++;
    }
    return cuenta;
}

/** ¿Es el paso actual el último visible? */
function _esUltimoPasoVisible() {
    for (let i = _tourIdx + 1; i < _tourPasosArr.length; i++) {
        const p = _tourPasosArr[i];
        if (!p.skipIfHidden || _elementoVisible(p.selector)) return false;
    }
    return true;
}

// ============================================================
// Spotlight (foco)
// ============================================================
let _selectorFocoActual = null;

function _iluminarElemento(selector) {
    _selectorFocoActual = selector;

    if (!selector) {
        _elFoco.style.display = 'none';
        return;
    }

    const el = document.querySelector(selector);
    if (!el) {
        _elFoco.style.display = 'none';
        return;
    }

    // Hacer scroll si es necesario
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });

    // Posicionar tras el scroll
    setTimeout(() => _reposicionarFoco(), 350);
}

function _reposicionarFoco() {
    const selector = _selectorFocoActual;
    if (!selector || !_tourActivo) return;
    const el = document.querySelector(selector);
    if (!el) { _elFoco.style.display = 'none'; return; }

    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
        _elFoco.style.display = 'none';
        return;
    }

    const margen = 8;
    _elFoco.style.display = 'block';
    _elFoco.style.top     = (rect.top  - margen) + 'px';
    _elFoco.style.left    = (rect.left - margen) + 'px';
    _elFoco.style.width   = (rect.width  + margen * 2) + 'px';
    _elFoco.style.height  = (rect.height + margen * 2) + 'px';
}

// ============================================================
// Cálculo de pose por dirección
// ============================================================
function _calcularPoseDireccion(selector) {
    if (!selector) return 'senala_derecha';

    const el = document.querySelector(selector);
    if (!el || !_elGuia) return 'senala_derecha';

    const rectEl   = el.getBoundingClientRect();
    const rectGuia = _elGuia.getBoundingClientRect();

    const cx = rectEl.left   + rectEl.width   / 2;
    const cy = rectEl.top    + rectEl.height  / 2;
    const gx = rectGuia.left + rectGuia.width / 2;
    const gy = rectGuia.top  + rectGuia.height / 2;

    const dx = cx - gx;
    const dy = cy - gy;

    if (Math.abs(dx) >= Math.abs(dy)) {
        return dx >= 0 ? 'senala_derecha' : 'senala_izquierda';
    } else {
        return dy < 0 ? 'senala_arriba' : 'senala_abajo';
    }
}

// ============================================================
// Visibilidad de elementos
// ============================================================
function _elementoVisible(selector) {
    if (!selector) return true;
    const el = document.querySelector(selector);
    if (!el) return false;
    const estilo = window.getComputedStyle(el);
    if (estilo.display === 'none' || estilo.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0;
}

// ============================================================
// Interacciones del usuario
// ============================================================
function _alClickGuia() {
    if (_tourActivo) {
        // Avanzar al siguiente paso
        _avanzarPaso();
        return;
    }
    // Iniciar tour de la pantalla actual (primera pose: saludo_mano)
    const pantalla = _pantallActual;
    if (!_pasos[pantalla] || _pasos[pantalla].length === 0) return;
    // Sobreescribir la pose del primer paso con saludo_mano al iniciar por clic
    _setPose('saludo_mano');
    setTimeout(() => iniciarTour(pantalla), 80);
}

function _teclaGlobal(e) {
    if (!_tourActivo) return;
    if (e.key === 'Escape') {
        e.preventDefault();
        _terminarTour(true);
    } else if (e.key === 'Enter' || e.key === 'ArrowRight') {
        // Solo si el foco está en la burbuja o fuera de inputs
        const tagActivo = document.activeElement ? document.activeElement.tagName : '';
        if (tagActivo === 'INPUT' || tagActivo === 'TEXTAREA') return;
        e.preventDefault();
        _avanzarPaso();
    } else if (e.key === 'ArrowLeft') {
        const tagActivo = document.activeElement ? document.activeElement.tagName : '';
        if (tagActivo === 'INPUT' || tagActivo === 'TEXTAREA') return;
        e.preventDefault();
        _retrocederPaso();
    }
}

// ============================================================
// Preferencias (servidor)
// ============================================================
async function _cargarPreferencias() {
    try {
        const r = await fetch('/api/preferencias');
        if (r.ok) {
            const d = await r.json();
            if (d && Array.isArray(d.tutoriales_vistos)) {
                _prefs = d;
            }
        }
    } catch (_) { /* sin conexión: usar prefs vacías */ }
}

function _marcarVisto(pantalla) {
    if (_prefs.tutoriales_vistos.includes(pantalla)) return;
    _prefs.tutoriales_vistos.push(pantalla);
    _guardarPreferencias();
}

async function _guardarPreferencias() {
    try {
        await fetch('/api/preferencias', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(_prefs),
        });
    } catch (_) { /* fallo silencioso */ }
}

async function _reiniciarTutoriales() {
    _prefs = { tutoriales_vistos: [] };
    try {
        await fetch('/api/preferencias', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reiniciar: true }),
        });
    } catch (_) { /* fallo silencioso */ }
    _terminarTour(false);
    alert('Los tutoriales se verán de nuevo la próxima vez que entres a cada pantalla.');
}

// ============================================================
// Botón de reinicio en el pie de la pantalla de inicio
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('btn-reiniciar-tutoriales');
    if (btn) {
        btn.addEventListener('click', _reiniciarTutoriales);
    }
});
