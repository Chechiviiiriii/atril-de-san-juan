/**
 * app.js — Lógica de la interfaz de Atril de San Juan
 * Agrupación Musical Stmo. Cristo de la Salud — Alcalá la Real
 */

'use strict';

// ============================================================
// Constantes / metadatos de la app (se actualizan desde /api/info)
// ============================================================
let _appNombre  = 'Atril de San Juan';
let _appVersion = '0.1.0';
let _appUrlRepo = 'https://github.com/Chechiviiiriii/atril-de-san-juan';

document.title = _appNombre;

// ============================================================
// Estado global
// ============================================================
const estado = {
    // Flujo activo: 'inicio' | 'nombres' | 'empalme'
    flujo: 'inicio',
    // Paso dentro del flujo nombres (1=subir, 2=revisar, 3=listo)
    pasoNombres: 1,

    // -- Flujo nombres --
    idTrabajo:      null,
    intervaloPoll:  null,
    resultado:      null,
    descargaUrl:    null,
    descargaNombre: null,
    // Correcciones en formato nuevo: {id: {texto?, x?, base?, tam?, fija?}}
    correcciones:   {},
    // Historial de deshacer / rehacer
    historial:   [],   // [{id, antes, despues}]
    redoStack:   [],   // [{id, antes, despues}]
    // Nota seleccionada y selector
    notaSeleccionadaId: null,
    notaActiva:     null,
    notaActualIdx:  0,
    dudosaIds:      [],
    notaSelTmp:     { nota: null, alt: '' },
    // Acordes: mapa acordeId→[notaIds ordenados agudo-grave], notaId→acordeId
    acordeMap:      {},   // {acordeId: [id, id, …]}
    notaAcorde:     {},   // {notaId: acordeId}
    // Estado temporal del selector de acorde: [{nota, alt}] por fila
    acordeSelTmp:   [],
    // Id del acorde abierto en el selector de acorde
    acordeActivo:   null,
    // Zoom
    zoom:           1.0,
    anchoBaseRef:   null,
    // Timer de recolocar
    _timerRecolocar: null,

    // -- Flujo empalme --
    archivosEmpalme: [],   // [{id, titulo, archivo, paginas, sha256, miniatura}]
    empalmeDescargaUrl:  null,
    empalmeDescargaNombre: null,
};

// ============================================================
// Utilidades DOM
// ============================================================
const $ = id => document.getElementById(id);
const scrollPags    = $('scroll-paginas');
const selectorNota  = $('selector-nota');
const modalFondo    = $('modal-fondo');

// ============================================================
// Arranque: obtener metadatos de la app y mostrar inicio
// ============================================================
(async function arrancar() {
    try {
        const r = await fetch('/api/info');
        if (r.ok) {
            const d = await r.json();
            _appNombre  = d.nombre  || _appNombre;
            _appVersion = d.version || _appVersion;
            _appUrlRepo = d.url_repo || _appUrlRepo;
            document.title = _appNombre;
            const elNombre = $('cabecera-nombre-app');
            if (elNombre) elNombre.textContent = _appNombre;
            const elInicioNombre = $('inicio-nombre-app');
            if (elInicioNombre) elInicioNombre.textContent = _appNombre;
        }
    } catch (_) { /* usa constantes por defecto */ }

    // Rellenar pie de licencia
    const pieVersion = $('pie-version');
    if (pieVersion) pieVersion.textContent = 'v' + _appVersion;
    const pieEnlace = $('pie-enlace-repo');
    if (pieEnlace) {
        pieEnlace.href = _appUrlRepo;
        pieEnlace.textContent = _appUrlRepo.replace('https://', '');
    }

    // Configurar botón de enlace en pywebview
    if (pieEnlace) {
        pieEnlace.addEventListener('click', e => {
            if (typeof window.pywebview !== 'undefined') {
                e.preventDefault();
                window.pywebview.api.abrir_enlace(_appUrlRepo).catch(() => {});
            }
            // En navegador funciona el target="_blank" nativo
        });
    }

    mostrarSeccion('inicio');
})();

// ============================================================
// Navegación entre secciones principales
// ============================================================

/** Muestra la sección indicada y oculta las demás. */
function mostrarSeccion(nombre) {
    const ids = ['paso-inicio','paso-subir','paso-revisar','paso-empalme','paso-listo'];
    ids.forEach(id => {
        const el = $(id);
        if (el) el.classList.toggle('activo', id === 'paso-' + nombre);
    });
    actualizarIndicador(nombre);
    // Notificar al módulo guía del cambio de pantalla.
    // Para 'revisar' el evento se lanza después, cuando los nombres ya están dibujados.
    if (nombre !== 'revisar') {
        document.dispatchEvent(new CustomEvent('pantalla', { detail: nombre }));
    }
}

function actualizarIndicador(seccion) {
    const ind = $('indicador-pasos');
    if (!ind) return;
    ind.innerHTML = '';

    if (seccion === 'inicio') return;

    const pasos = seccion === 'empalme' || seccion === 'listo-empalme'
        ? [['1', 'Ordenar'], ['2', 'Listo']]
        : [['1', 'Subir'], ['2', 'Revisar'], ['3', 'Listo']];

    const activo = seccion === 'subir' ? 1
        : seccion === 'revisar' ? 2
        : seccion === 'listo' ? 3
        : seccion === 'empalme' ? 1
        : 2;

    pasos.forEach(([num, nombre], i) => {
        const n = i + 1;
        if (i > 0) {
            const sep = document.createElement('span');
            sep.className = 'paso-sep';
            sep.textContent = '›';
            ind.appendChild(sep);
        }
        const span = document.createElement('span');
        span.className = 'paso-ind' + (n === activo ? ' activo' : n < activo ? ' hecho' : '');
        span.innerHTML = `<span class="paso-num">${num}</span><span class="paso-nombre">${nombre}</span>`;
        ind.appendChild(span);
    });
}

// Botón de inicio en la cabecera
$('btn-inicio-cabecera').addEventListener('click', () => {
    if (estado.intervaloPoll) clearInterval(estado.intervaloPoll);
    cerrarSelector();
    estado.flujo = 'inicio';
    mostrarSeccion('inicio');
});

// Tarjetas de función en la pantalla de inicio
$('btn-funcion-nombres').addEventListener('click', () => {
    estado.flujo = 'nombres';
    mostrarEstadoCarga('carga');
    mostrarSeccion('subir');
});

$('btn-funcion-empalme').addEventListener('click', () => {
    estado.flujo = 'empalme';
    mostrarSeccion('empalme');
});

// ============================================================
// Paso SUBIR — Subir archivo PDF
// ============================================================

const zonaCarga = $('zona-carga');
const inputArch = $('input-archivo');
const faseTexto = $('fase-texto');
const errorMsg  = $('error-mensaje');

// Imagen hero de fondo (el cartel de la agrupación)
(function() {
    const heroImgs = document.querySelectorAll('.hero-imagen');
    const img = new Image();
    img.onload = () => {
        heroImgs.forEach(hi => {
            hi.style.backgroundImage = "url('img/cabecera.jpg')";
        });
    };
    img.src = 'img/cabecera.jpg';
})();

function mostrarEstadoCarga(nombre) {
    $('estado-carga').style.display     = (nombre === 'carga')      ? '' : 'none';
    $('estado-procesando').style.display = (nombre === 'procesando') ? '' : 'none';
    $('estado-error').style.display     = (nombre === 'error')      ? '' : 'none';
}

function mostrarError(msg) {
    errorMsg.textContent = msg;
    mostrarEstadoCarga('error');
    mostrarSeccion('subir');
}

// Drag & drop
zonaCarga.addEventListener('dragover', e => { e.preventDefault(); zonaCarga.classList.add('arrastrando'); });
zonaCarga.addEventListener('dragleave', () => zonaCarga.classList.remove('arrastrando'));
zonaCarga.addEventListener('drop', e => {
    e.preventDefault();
    zonaCarga.classList.remove('arrastrando');
    const arch = e.dataTransfer.files[0];
    if (arch) procesarArchivo(arch);
});
zonaCarga.addEventListener('click', () => inputArch.click());
zonaCarga.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') inputArch.click(); });
$('btn-elegir').addEventListener('click', e => { e.stopPropagation(); inputArch.click(); });
inputArch.addEventListener('change', () => {
    if (inputArch.files[0]) procesarArchivo(inputArch.files[0]);
    inputArch.value = '';
});
$('btn-reintentar').addEventListener('click', () => mostrarEstadoCarga('carga'));

function procesarArchivo(arch) {
    if (!arch.name.toLowerCase().endsWith('.pdf')) {
        mostrarError('Solo se aceptan archivos PDF (.pdf).');
        return;
    }
    mostrarEstadoCarga('procesando');
    faseTexto.textContent = 'Subiendo archivo…';

    fetch('/api/trabajos', {
        method: 'POST',
        headers: { 'X-Nombre-Archivo': encodeURIComponent(arch.name) },
        body: arch,
    })
    .then(r => r.json())
    .then(d => {
        if (d.error) { mostrarError(d.error); return; }
        estado.idTrabajo = d.id;
        iniciarPolling();
    })
    .catch(err => mostrarError('Error al subir: ' + err.message));
}

// ============================================================
// Polling de estado
// ============================================================

function iniciarPolling() {
    if (estado.intervaloPoll) clearInterval(estado.intervaloPoll);
    estado.intervaloPoll = setInterval(consultarEstado, 700);
}

function consultarEstado() {
    fetch(`/api/trabajos/${estado.idTrabajo}`)
    .then(r => r.json())
    .then(d => {
        if (d.estado === 'procesando') {
            faseTexto.textContent = d.fase || 'Procesando…';
        } else if (d.estado === 'listo') {
            clearInterval(estado.intervaloPoll);
            estado.resultado = d.resultado;
            cargarRevision(d.resultado);
        } else if (d.estado === 'error') {
            clearInterval(estado.intervaloPoll);
            mostrarError(d.error || 'Error desconocido.');
        }
    })
    .catch(err => {
        clearInterval(estado.intervaloPoll);
        mostrarError('Error de conexión: ' + err.message);
    });
}

// ============================================================
// Paso REVISAR — Cargar revisión
// ============================================================

function cargarRevision(res) {
    estado.resultado    = res;
    estado.correcciones = {};
    estado.historial    = [];
    estado.redoStack    = [];
    estado.dudosaIds    = [];
    estado.acordeMap    = {};
    estado.notaAcorde   = {};
    estado.acordeSelTmp = [];
    estado.acordeActivo = null;

    const notas = res.notas || [];

    // Construir mapas de acordes: acordeId → [notaIds ordenados agudo-grave]
    // El servidor envía acorde: int|null; la ordenación ya la hace superponer.py (y bbox)
    const acordesVisto = new Set();
    notas.forEach(n => {
        if (n.acorde != null) {
            if (!estado.acordeMap[n.acorde]) estado.acordeMap[n.acorde] = [];
            estado.acordeMap[n.acorde].push(n.id);
            estado.notaAcorde[n.id] = n.acorde;
        }
    });
    // Ordenar cada grupo por bbox y (agudo = y menor primero)
    const notaPorId = {};
    notas.forEach(n => { notaPorId[n.id] = n; });
    Object.keys(estado.acordeMap).forEach(ak => {
        estado.acordeMap[ak].sort((a, b) => {
            const ya = notaPorId[a]?.cabeza[1] ?? 0;
            const yb = notaPorId[b]?.cabeza[1] ?? 0;
            return ya - yb;
        });
    });

    // dudosaIds: una entrada por nota suelta dudosa/deducida, y
    // UNA entrada (el primer id del grupo) por acorde dudoso
    const acordeRepresentante = new Set();  // acordeIds ya añadidos
    notas.forEach(n => {
        if (n.estado !== 'dudosa' && n.estado !== 'deducida') return;
        if (n.acorde != null) {
            if (!acordeRepresentante.has(n.acorde)) {
                acordeRepresentante.add(n.acorde);
                // Representante = primer id del grupo (agudo)
                const rep = estado.acordeMap[n.acorde][0];
                estado.dudosaIds.push(rep);
            }
        } else {
            estado.dudosaIds.push(n.id);
        }
    });
    estado.notaActualIdx = 0;

    renderizarCabeceraBanda(res);
    renderizarPaginas(res);
    actualizarContador();
    renderizarListaDudosas(notas);
    actualizarNavDudosas();
    actualizarBtnDeshacer();

    mostrarSeccion('revisar');

    // Zoom inicial: ajustar al ancho del scroll con mínimo 125%
    setTimeout(() => {
        ajustarZoomInicial();
        if (estado.dudosaIds.length > 0) irANota(estado.dudosaIds[0]);
        // Notificar al guía que revisar ya está completamente pintado
        document.dispatchEvent(new CustomEvent('revisarListo'));
    }, 300);
}

function ajustarZoomInicial() {
    const scroll = scrollPags;
    const contenedorAncho = scroll.clientWidth - 96;
    if (!estado.anchoBaseRef || !contenedorAncho) return;

    // Render the first page at (contenedorAncho / anchoBaseRef) * pt_to_px ratio.
    // Zoom=1 means page fills width. We want at least 125%.
    const zoomAjuste = 1.0;
    const zoomMinimo = 1.25;
    aplicarZoom(Math.max(zoomMinimo, zoomAjuste));
}

function renderizarCabeceraBanda(res) {
    const listaCambios = $('lista-cambios');
    listaCambios.innerHTML = '';
    (res.cambios || []).slice(0, 6).forEach(c => {
        const li = document.createElement('li');
        li.textContent = c;
        listaCambios.appendChild(li);
    });

    const listaAvisos = $('lista-avisos');
    listaAvisos.innerHTML = '';
    (res.avisos || []).forEach(a => {
        const div = document.createElement('div');
        div.className = 'aviso-item';
        div.innerHTML = '<span aria-hidden="true">⚠</span><span></span>';
        div.querySelector('span:last-child').textContent = a;
        listaAvisos.appendChild(div);
    });
}

// ============================================================
// Renderizado de páginas + overlays
// ============================================================

let resizeObs = null;

function renderizarPaginas(res) {
    scrollPags.innerHTML = '';
    if (resizeObs) resizeObs.disconnect();
    resizeObs = new ResizeObserver(() => reposicionarTodasLasNotas());

    const paginasInfo = res.paginas_info || [];
    const notas = res.notas || [];

    if (paginasInfo.length > 0) {
        estado.anchoBaseRef = paginasInfo[0].ancho;
    }

    paginasInfo.forEach((pag, idx) => {
        const notasPag = notas.filter(n => n.pagina === idx);
        const env = crearEnvolturaPagina(idx, pag, notasPag, res.nombre_archivo);
        scrollPags.appendChild(env);
        resizeObs.observe(env);
    });
}

function crearEnvolturaPagina(idx, pag, notas, nombreArch) {
    const env = document.createElement('div');
    env.className = 'pagina-envoltorio';
    env.dataset.paginaIdx = idx;
    env.dataset.anchoPoints = pag.ancho;
    env.dataset.altoPoints  = pag.alto;

    const img = document.createElement('img');
    img.className = 'pagina-img';
    img.src = pag.imagen;
    img.alt = `Página ${idx + 1} de ${nombreArch || 'la partitura'}`;
    img.draggable = false;

    const overlay = document.createElement('div');
    overlay.className = 'notas-overlay';
    overlay.dataset.paginaIdx = idx;

    notas.forEach(nota => {
        if (nota.x == null || nota.base == null || nota.tam == null) return;
        overlay.appendChild(crearElementoNota(nota, pag));
    });

    env.appendChild(img);
    env.appendChild(overlay);

    img.addEventListener('load', () => reposicionarNotasPagina(env));
    return env;
}

function crearElementoNota(nota, pag) {
    const el = document.createElement('span');
    el.className = `nota-nombre estado-${nota.estado}`;
    el.dataset.id          = nota.id;
    el.dataset.anchoPoints = pag.ancho;
    el.dataset.altoPoints  = pag.alto;
    el.dataset.x           = nota.x;
    el.dataset.base        = nota.base;
    el.dataset.tam         = nota.tam;
    el.dataset.tamOrig     = nota.tam;    // tamaño original para restablecer
    el.dataset.xOrig       = nota.x;     // posición original para restablecer
    el.dataset.baseOrig    = nota.base;
    el.dataset.cabeza      = JSON.stringify(nota.cabeza);
    el.dataset.texto       = nota.texto;
    el.dataset.textoOrig   = nota.texto;
    el.dataset.estado      = nota.estado;
    el.dataset.motivo      = nota.motivo || '';
    el.textContent         = nota.texto;

    // Gestión de eventos: distinguir clic de arrastre
    let pointerMovido = false;
    let pointerInicioX = 0;
    let pointerInicioY = 0;
    let xPtInicio = 0, basePtInicio = 0;
    let draggingNow = false;

    el.addEventListener('pointerdown', e => {
        if (e.button !== 0) return;
        e.stopPropagation();
        pointerMovido = false;
        pointerInicioX = e.clientX;
        pointerInicioY = e.clientY;
        // Guardar posición actual en puntos PDF
        const env = el.closest('.pagina-envoltorio');
        const img = env.querySelector('.pagina-img');
        const s = img.clientWidth / Number(env.dataset.anchoPoints);
        xPtInicio    = Number(el.dataset.x);
        basePtInicio = Number(el.dataset.base);

        el.setPointerCapture(e.pointerId);
    });

    el.addEventListener('pointermove', e => {
        if (!el.hasPointerCapture(e.pointerId)) return;
        const dx = e.clientX - pointerInicioX;
        const dy = e.clientY - pointerInicioY;
        if (!draggingNow && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
            pointerMovido = true;
            draggingNow = true;
            el.classList.add('arrastrando');
            cerrarSelector();
            // Marcar como nota seleccionada para el handle
            seleccionarNota(nota.id);
        }
        if (draggingNow) {
            const env = el.closest('.pagina-envoltorio');
            const img = env.querySelector('.pagina-img');
            const anchoPoints = Number(env.dataset.anchoPoints);
            const altoPoints  = Number(env.dataset.altoPoints);
            const s = img.clientWidth / anchoPoints;

            let nuevoX    = xPtInicio    + dx / s;
            let nuevoBase = basePtInicio + dy / s;

            // Limitar dentro de la página
            const tam = Number(el.dataset.tam);
            nuevoX    = Math.max(0, Math.min(anchoPoints - 2, nuevoX));
            nuevoBase = Math.max(tam, Math.min(altoPoints, nuevoBase));

            el.dataset.x    = nuevoX;
            el.dataset.base = nuevoBase;

            // Actualizar posición visual en tiempo real
            el.style.left = (nuevoX * s).toFixed(2) + 'px';
            el.style.top  = ((nuevoBase - tam * 0.78) * s).toFixed(2) + 'px';

            moverHandle(el);
        }
    });

    el.addEventListener('pointerup', e => {
        if (!el.hasPointerCapture(e.pointerId)) return;
        el.releasePointerCapture(e.pointerId);
        if (draggingNow) {
            draggingNow = false;
            el.classList.remove('arrastrando');
            const nuevoX    = Number(el.dataset.x);
            const nuevoBase = Number(el.dataset.base);
            if (nuevoX !== xPtInicio || nuevoBase !== basePtInicio) {
                registrarHistorial(nota.id,
                    { x: xPtInicio, base: basePtInicio },
                    { x: nuevoX, base: nuevoBase }
                );
                const tam = Number(el.dataset.tam);
                aplicarCorreccionPosicion(nota.id, nuevoX, nuevoBase, tam, true);
                programarRecolocar();
            }
        } else if (!pointerMovido) {
            // Es un clic simple
            irANota(nota.id);
            abrirSelector(nota.id);
        }
    });

    el.addEventListener('pointercancel', () => {
        draggingNow = false;
        el.classList.remove('arrastrando');
    });

    // Ctrl+rueda para redimensionar
    el.addEventListener('wheel', e => {
        if (!e.ctrlKey) return;
        e.preventDefault();
        const id = nota.id;
        const tamActual = obtenerTamActual(id);
        const delta = e.deltaY < 0 ? 0.5 : -0.5;
        const nuevoTam = Math.min(14, Math.max(5, tamActual + delta));
        if (nuevoTam !== tamActual) {
            registrarHistorial(id, { tam: tamActual }, { tam: nuevoTam });
            aplicarCorreccionTam(id, nuevoTam, true);
            if (estado.notaActiva === id) actualizarUITam();
            programarRecolocar();
        }
    }, { passive: false });

    return el;
}

// ============================================================
// Handle de redimensionado
// ============================================================

let _handleActual = null;

function crearHandle(el) {
    quitarHandle();
    const handle = document.createElement('div');
    handle.className = 'redim-handle';
    handle.title = 'Arrastrar para redimensionar';
    const overlay = el.closest('.notas-overlay');
    if (!overlay) return;
    overlay.appendChild(handle);
    posicionarHandle(handle, el);
    _handleActual = handle;

    let hPointerInicioX = 0;
    let hTamInicio = 0;
    const id = el.dataset.id;

    handle.addEventListener('pointerdown', e => {
        e.stopPropagation();
        e.preventDefault();
        hPointerInicioX = e.clientX;
        hTamInicio = obtenerTamActual(id);
        handle.setPointerCapture(e.pointerId);
    });

    handle.addEventListener('pointermove', e => {
        if (!handle.hasPointerCapture(e.pointerId)) return;
        const dx = e.clientX - hPointerInicioX;
        const env = el.closest('.pagina-envoltorio');
        const img = env.querySelector('.pagina-img');
        const s = img.clientWidth / Number(env.dataset.anchoPoints);
        // Convertir píxeles de arrastre a puntos PDF
        const nuevoTam = Math.min(14, Math.max(5, hTamInicio + dx / s));
        aplicarCorreccionTam(id, nuevoTam, false);  // sin guardar historial aún
        el.dataset.tam = nuevoTam;
        reposicionarNotasPagina(env);
        posicionarHandle(handle, el);
        if (estado.notaActiva === Number(id)) actualizarUITam();
    });

    handle.addEventListener('pointerup', e => {
        if (!handle.hasPointerCapture(e.pointerId)) return;
        handle.releasePointerCapture(e.pointerId);
        const nuevoTam = obtenerTamActual(id);
        if (Math.abs(nuevoTam - hTamInicio) > 0.05) {
            registrarHistorial(id,
                { tam: hTamInicio },
                { tam: nuevoTam }
            );
            aplicarCorreccionTam(id, nuevoTam, true);
            programarRecolocar();
        }
    });
}

function posicionarHandle(handle, el) {
    const elRect = el.getBoundingClientRect();
    const overlayRect = el.closest('.notas-overlay').getBoundingClientRect();
    handle.style.left = (elRect.right  - overlayRect.left - 5) + 'px';
    handle.style.top  = (elRect.bottom - overlayRect.top  - 5) + 'px';
}

function moverHandle(el) {
    if (_handleActual && el.classList.contains('seleccionada')) {
        posicionarHandle(_handleActual, el);
    }
}

function quitarHandle() {
    if (_handleActual) {
        _handleActual.remove();
        _handleActual = null;
    }
}

// ============================================================
// Posicionamiento de notas
// ============================================================

function reposicionarNotasPagina(env) {
    const img = env.querySelector('.pagina-img');
    if (!img.naturalWidth) return;
    const anchoPoints = Number(env.dataset.anchoPoints);
    const s = img.clientWidth / anchoPoints;

    const overlay = env.querySelector('.notas-overlay');
    overlay.style.width  = img.clientWidth  + 'px';
    overlay.style.height = img.clientHeight + 'px';

    overlay.querySelectorAll('.nota-nombre').forEach(el => {
        const x    = Number(el.dataset.x);
        const base = Number(el.dataset.base);
        const tam  = Number(el.dataset.tam);
        el.style.left     = (x * s).toFixed(2) + 'px';
        el.style.top      = ((base - tam * 0.78) * s).toFixed(2) + 'px';
        el.style.fontSize = (tam * s).toFixed(2) + 'px';
    });

    // Mover ring si está visible
    const ring = overlay.querySelector('.cabeza-ring');
    if (ring) actualizarRing(ring, s);

    // Mover handle si hay uno
    if (_handleActual) {
        const selEl = overlay.querySelector('.nota-nombre.seleccionada');
        if (selEl) posicionarHandle(_handleActual, selEl);
    }
}

function reposicionarTodasLasNotas() {
    document.querySelectorAll('.pagina-envoltorio').forEach(env => {
        reposicionarNotasPagina(env);
    });
}

function actualizarRing(ring, s) {
    const cabeza = JSON.parse(ring.dataset.cabeza || '[]');
    if (!cabeza.length) return;
    const [x0, y0, x1, y1] = cabeza;
    ring.style.left   = (x0 * s - 2).toFixed(2) + 'px';
    ring.style.top    = (y0 * s - 2).toFixed(2) + 'px';
    ring.style.width  = ((x1 - x0) * s + 4).toFixed(2) + 'px';
    ring.style.height = ((y1 - y0) * s + 4).toFixed(2) + 'px';
}

// ============================================================
// Zoom
// ============================================================

function aplicarZoom(zoom) {
    estado.zoom = zoom;
    $('zoom-texto').textContent = Math.round(zoom * 100) + '%';

    const scroll   = scrollPags;
    const contenedorAncho = scroll.clientWidth - 96;

    document.querySelectorAll('.pagina-envoltorio').forEach(env => {
        env.style.width = (contenedorAncho * zoom) + 'px';
    });
    reposicionarTodasLasNotas();
}

$('zoom-menos').addEventListener('click', () => aplicarZoom(Math.max(0.3, estado.zoom - 0.15)));
$('zoom-mas').addEventListener('click',   () => aplicarZoom(Math.min(3.0, estado.zoom + 0.15)));
$('zoom-ajustar').addEventListener('click', () => ajustarZoomInicial());

// Ctrl+rueda en el scroll de páginas para zoom
scrollPags.addEventListener('wheel', e => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.1 : -0.1;
    aplicarZoom(Math.min(3.0, Math.max(0.3, estado.zoom + delta)));
}, { passive: false });

// ============================================================
// Historial (deshacer / rehacer)
// ============================================================

function registrarHistorial(id, antes, despues) {
    estado.historial.push({ id: String(id), antes, despues });
    estado.redoStack = [];
    actualizarBtnDeshacer();
}

function actualizarBtnDeshacer() {
    const btn = $('btn-deshacer');
    if (btn) btn.disabled = estado.historial.length === 0;
}

function deshacer() {
    if (estado.historial.length === 0) return;
    const entrada = estado.historial.pop();
    estado.redoStack.push(entrada);
    if (entrada.esAcorde) {
        entrada.entradas.forEach(e => aplicarEstadoNota(e.id, e.antes));
    } else {
        aplicarEstadoNota(entrada.id, entrada.antes);
    }
    actualizarBtnDeshacer();
    programarRecolocar();
}

function rehacer() {
    if (estado.redoStack.length === 0) return;
    const entrada = estado.redoStack.pop();
    estado.historial.push(entrada);
    if (entrada.esAcorde) {
        entrada.entradas.forEach(e => aplicarEstadoNota(e.id, e.despues));
    } else {
        aplicarEstadoNota(entrada.id, entrada.despues);
    }
    actualizarBtnDeshacer();
    programarRecolocar();
}

/** Aplica un estado guardado (antes/despues) a la nota. */
function aplicarEstadoNota(id, estadoGuardado) {
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    if (!el) return;

    if ('texto' in estadoGuardado) {
        const texto = estadoGuardado.texto;
        el.textContent = texto;
        el.dataset.texto = texto;
        el.classList.remove('estado-dudosa','estado-deducida');
        el.classList.add('estado-confirmada');
        actualizarItemDudosa(id, texto);
    }
    if ('x' in estadoGuardado) el.dataset.x    = estadoGuardado.x;
    if ('base' in estadoGuardado) el.dataset.base = estadoGuardado.base;
    if ('tam' in estadoGuardado) el.dataset.tam  = estadoGuardado.tam;

    // Actualizar correcciones
    const corr = estado.correcciones[id] || {};
    if ('texto' in estadoGuardado) corr.texto = estadoGuardado.texto;
    if ('x' in estadoGuardado) { corr.x = estadoGuardado.x; corr.fija = true; }
    if ('base' in estadoGuardado) { corr.base = estadoGuardado.base; corr.fija = true; }
    if ('tam' in estadoGuardado) { corr.tam = estadoGuardado.tam; corr.fija = true; }
    estado.correcciones[id] = corr;

    const env = el.closest('.pagina-envoltorio');
    if (env) reposicionarNotasPagina(env);

    actualizarContador();
    if (estado.notaActiva == id) actualizarUITam();
}

$('btn-deshacer').addEventListener('click', deshacer);

// ============================================================
// Correcciones: texto, posición, tamaño
// ============================================================

function obtenerTamActual(id) {
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    if (el) return Number(el.dataset.tam);
    const corr = estado.correcciones[id];
    if (corr && 'tam' in corr) return corr.tam;
    return 9.5;
}

function aplicarCorreccionTexto(id, texto) {
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    const antes = { texto: el ? el.dataset.texto : '' };
    const despues = { texto };

    registrarHistorial(id, antes, despues);

    if (el) {
        el.textContent = texto;
        el.dataset.texto = texto;
        el.classList.remove('estado-dudosa','estado-deducida');
        el.classList.add('estado-confirmada');
    }
    const corr = estado.correcciones[id] || {};
    corr.texto = texto;
    estado.correcciones[id] = corr;

    actualizarItemDudosa(id, texto);
    actualizarContador();
}

function aplicarCorreccionPosicion(id, x, base, tam, guardarEnCorr) {
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    if (el) {
        el.dataset.x    = x;
        el.dataset.base = base;
        el.dataset.tam  = tam;
        const env = el.closest('.pagina-envoltorio');
        if (env) reposicionarNotasPagina(env);
    }
    if (guardarEnCorr) {
        const corr = estado.correcciones[id] || {};
        corr.x    = x;
        corr.base = base;
        corr.tam  = tam;
        corr.fija = true;
        estado.correcciones[id] = corr;
    }
}

function aplicarCorreccionTam(id, tam, guardarEnCorr) {
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    if (el) {
        el.dataset.tam = tam;
        const env = el.closest('.pagina-envoltorio');
        if (env) reposicionarNotasPagina(env);
    }
    if (guardarEnCorr) {
        const corr = estado.correcciones[id] || {};
        corr.tam  = tam;
        corr.fija = true;
        estado.correcciones[id] = corr;
    }
}

// ============================================================
// Recolocar con debounce
// ============================================================

function programarRecolocar() {
    if (estado._timerRecolocar) clearTimeout(estado._timerRecolocar);
    estado._timerRecolocar = setTimeout(ejecutarRecolocar, 300);
}

function ejecutarRecolocar() {
    if (!estado.idTrabajo) return;

    // Construir correcciones con datos actuales de los elementos
    const corr = {};
    document.querySelectorAll('.nota-nombre').forEach(el => {
        const id = el.dataset.id;
        const c  = estado.correcciones[id] || {};
        corr[id] = Object.assign({}, c, {
            x:    Number(el.dataset.x),
            base: Number(el.dataset.base),
            tam:  Number(el.dataset.tam),
        });
        if (Object.keys(corr[id]).length > 0) corr[id].fija = true;
    });

    fetch(`/api/trabajos/${estado.idTrabajo}/recolocar`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ correcciones: corr }),
    })
    .then(r => r.json())
    .then(d => {
        if (d.posiciones) {
            d.posiciones.forEach(pos => {
                // Solo actualizar notas NO fijas (las fijas ya están donde el usuario las puso)
                const corrNota = estado.correcciones[pos.id];
                if (corrNota && corrNota.fija) return;

                const el = document.querySelector(`.nota-nombre[data-id="${pos.id}"]`);
                if (!el) return;
                if (pos.x    != null) el.dataset.x    = pos.x;
                if (pos.base != null) el.dataset.base = pos.base;
                if (pos.tam  != null) el.dataset.tam  = pos.tam;
                const env = el.closest('.pagina-envoltorio');
                if (env) reposicionarNotasPagina(env);
            });
        }
    })
    .catch(() => { /* fallo silencioso */ });
}

// ============================================================
// Barra lateral: contador y lista de dudosas
// ============================================================

function _acordeConfirmado(id) {
    /** True si el id es representante de un acorde y todas sus notas tienen corrección de texto. */
    const acordeId = estado.notaAcorde[id];
    if (acordeId == null) {
        // Nota suelta
        const corr = estado.correcciones[id];
        return !!(corr && 'texto' in corr);
    }
    // Acorde: todas sus notas deben tener corrección
    const ids = estado.acordeMap[acordeId] || [];
    return ids.every(nid => {
        const c = estado.correcciones[nid];
        return c && 'texto' in c;
    });
}

function actualizarContador() {
    const pendientes = estado.dudosaIds.filter(id => !_acordeConfirmado(id)).length;
    const numEl = $('contador-num');
    const etEl  = $('contador-etiqueta');

    if (pendientes === 0 && estado.dudosaIds.length > 0) {
        numEl.textContent = '✓ Todo revisado';
        numEl.className = 'contador-num todo-ok';
        etEl.textContent = '';
    } else if (estado.dudosaIds.length === 0) {
        numEl.textContent = '✓ Sin dudas';
        numEl.className = 'contador-num todo-ok';
        etEl.textContent = '';
    } else {
        numEl.textContent = pendientes;
        numEl.className = 'contador-num';
        etEl.textContent = pendientes === 1 ? 'nota por revisar' : 'notas por revisar';
    }
}

function _textosAcorde(acordeId) {
    /** Devuelve los textos actuales de las notas de un acorde (agudo→grave). */
    const notas = estado.resultado ? (estado.resultado.notas || []) : [];
    const ids = estado.acordeMap[acordeId] || [];
    return ids.map(nid => {
        const corr = estado.correcciones[nid];
        if (corr && 'texto' in corr) return corr.texto;
        const nota = notas.find(n => n.id === nid);
        return nota ? nota.texto : '?';
    });
}

function renderizarListaDudosas(notas) {
    const lista = $('lista-dudosas');
    lista.innerHTML = '';
    estado.dudosaIds.forEach(id => {
        const nota = notas.find(n => n.id === id);
        if (!nota) return;
        const acordeId = estado.notaAcorde[id];
        if (acordeId != null) {
            lista.appendChild(crearItemAcorde(nota, acordeId));
        } else {
            lista.appendChild(crearItemDudosa(nota));
        }
    });
}

function crearItemDudosa(nota) {
    const li = document.createElement('li');
    li.className = 'item-dudosa';
    li.dataset.id = nota.id;

    const loc = document.createElement('div');
    loc.className = 'item-dudosa-loc';
    const partes = [];
    if (nota.linea)  partes.push(`Línea ${nota.linea}`);
    if (nota.compas) partes.push(`compás ~${nota.compas}`);
    loc.textContent = partes.join(' · ');

    const info = document.createElement('div');
    info.className = 'item-dudosa-info';

    const notaEl = document.createElement('span');
    notaEl.className = 'item-dudosa-nota';
    notaEl.textContent = nota.texto;
    info.appendChild(notaEl);

    const motivo = document.createElement('div');
    motivo.className = 'item-dudosa-motivo';
    motivo.textContent = nota.motivo || '';

    li.appendChild(loc);
    li.appendChild(info);
    li.appendChild(motivo);

    li.addEventListener('click', () => {
        const idx = estado.dudosaIds.indexOf(nota.id);
        if (idx >= 0) estado.notaActualIdx = idx;
        irANota(nota.id);
        abrirSelector(nota.id);
        actualizarNavDudosas();
    });
    return li;
}

function crearItemAcorde(nota, acordeId) {
    const li = document.createElement('li');
    li.className = 'item-dudosa item-dudosa-acorde';
    li.dataset.id = nota.id;
    li.dataset.acordeId = acordeId;

    const loc = document.createElement('div');
    loc.className = 'item-dudosa-loc';
    const partes = [];
    if (nota.linea)  partes.push(`Línea ${nota.linea}`);
    if (nota.compas) partes.push(`compás ~${nota.compas}`);
    loc.textContent = partes.join(' · ');

    const info = document.createElement('div');
    info.className = 'item-dudosa-info';

    const notaEl = document.createElement('span');
    notaEl.className = 'item-dudosa-nota';
    const textos = _textosAcorde(acordeId);
    notaEl.textContent = 'Acorde: ' + textos.join(' + ');
    info.appendChild(notaEl);

    const motivo = document.createElement('div');
    motivo.className = 'item-dudosa-motivo';
    motivo.textContent = 'Acorde: comprueba sus notas';

    li.appendChild(loc);
    li.appendChild(info);
    li.appendChild(motivo);

    li.addEventListener('click', () => {
        const idx = estado.dudosaIds.indexOf(nota.id);
        if (idx >= 0) estado.notaActualIdx = idx;
        irANota(nota.id);
        abrirSelector(nota.id);
        actualizarNavDudosas();
    });
    return li;
}

function actualizarItemDudosa(id, texto) {
    // Para nota suelta
    const li = document.querySelector(`.item-dudosa[data-id="${id}"]`);
    if (!li) return;
    const acordeId = li.dataset.acordeId != null ? Number(li.dataset.acordeId) : null;
    if (acordeId != null && !isNaN(acordeId)) {
        // Actualizar texto del acorde
        const notaEl = li.querySelector('.item-dudosa-nota');
        if (notaEl) notaEl.textContent = 'Acorde: ' + _textosAcorde(acordeId).join(' + ');
        li.classList.toggle('confirmada', _acordeConfirmado(id));
    } else {
        li.querySelector('.item-dudosa-nota').textContent = texto;
        const corr = estado.correcciones[id];
        li.classList.toggle('confirmada', !!(corr && 'texto' in corr));
    }
}

function actualizarNavDudosas() {
    const total = estado.dudosaIds.length;
    const idx   = estado.notaActualIdx;
    $('nav-pos').textContent = total > 0 ? `${idx + 1} / ${total}` : '';
    $('btn-anterior').disabled = idx <= 0;
    $('btn-siguiente').disabled = idx >= total - 1;
    $('nav-dudosas').style.display = total > 0 ? '' : 'none';
}

$('btn-anterior').addEventListener('click', () => navegarDudosa(-1));
$('btn-siguiente').addEventListener('click', () => navegarDudosa(1));

function navegarDudosa(delta) {
    const nuevo = estado.notaActualIdx + delta;
    if (nuevo < 0 || nuevo >= estado.dudosaIds.length) return;
    estado.notaActualIdx = nuevo;
    const id = estado.dudosaIds[nuevo];
    irANota(id);
    abrirSelector(id);
    actualizarNavDudosas();
}

// ============================================================
// Scroll a nota + highlight cabeza + handle
// ============================================================

function seleccionarNota(id) {
    document.querySelectorAll('.nota-nombre.seleccionada').forEach(e => {
        e.classList.remove('seleccionada');
    });
    document.querySelectorAll('.cabeza-ring').forEach(r => r.remove());
    quitarHandle();

    estado.notaSeleccionadaId = id;
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    if (!el) return;

    el.classList.add('seleccionada');

    const overlay = el.closest('.notas-overlay');
    const env     = el.closest('.pagina-envoltorio');
    const img     = env.querySelector('.pagina-img');
    const s = img.clientWidth / Number(env.dataset.anchoPoints);

    const cabeza = JSON.parse(el.dataset.cabeza || '[]');
    if (cabeza.length === 4) {
        const ring = document.createElement('div');
        ring.className = 'cabeza-ring';
        ring.dataset.cabeza = el.dataset.cabeza;
        actualizarRing(ring, s);
        overlay.appendChild(ring);
    }

    crearHandle(el);
}

function irANota(id) {
    seleccionarNota(id);

    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);

    // Destacar en lista lateral
    document.querySelectorAll('.item-dudosa').forEach(li => li.classList.remove('activo'));
    const liActivo = document.querySelector(`.item-dudosa[data-id="${id}"]`);
    if (liActivo) {
        liActivo.classList.add('activo');
        liActivo.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

// ============================================================
// Selector de nota (popover)
// ============================================================

const NOTAS = ['Do', 'Re', 'Mi', 'Fa', 'Sol', 'La', 'Si'];
const TAM_MIN = 5;
const TAM_MAX = 14;
const TAM_PASO = 0.5;

function parsearTextoNota(texto) {
    for (const nota of NOTAS) {
        if (texto.startsWith(nota)) {
            const resto = texto.slice(nota.length);
            let alt = '';
            if (resto.startsWith('bb'))      alt = 'bb';
            else if (resto.startsWith('##')) alt = '##';
            else if (resto.startsWith('b'))  alt = 'b';
            else if (resto.startsWith('#'))  alt = '#';
            return { nota, alt };
        }
    }
    if (texto === '·' || texto === '«·»') return { nota: '·', alt: '' };
    return { nota: '?', alt: '' };
}

function construirTextoNota(nota, alt) {
    if (nota === '·' || nota === '?' || nota == null) return nota || '?';
    return nota + alt;
}

function abrirSelector(id) {
    // Si la nota pertenece a un acorde, abrir el selector de acorde
    const acordeId = estado.notaAcorde[id];
    if (acordeId != null) {
        abrirSelectorAcorde(acordeId);
        return;
    }
    cerrarSelector();
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    if (!el) return;

    estado.notaActiva = id;

    const textoOrig = el.dataset.textoOrig || el.dataset.texto;
    $('prop-texto').textContent = textoOrig;

    // Inicializar con texto actual
    const corr = estado.correcciones[id];
    const textoActual = (corr && 'texto' in corr) ? corr.texto : el.dataset.texto;
    const { nota, alt } = parsearTextoNota(textoActual);
    estado.notaSelTmp = { nota, alt };
    actualizarUISelector();
    actualizarUITam();

    posicionarSelector(el);
    selectorNota.classList.add('visible');
    document.addEventListener('keydown', teclaSelector);
    document.addEventListener('pointerdown', clicFueraSelectorHandler, { capture: true, once: true });
}

function cerrarSelector() {
    selectorNota.classList.remove('visible');
    document.removeEventListener('keydown', teclaSelector);
    estado.notaActiva = null;
    cerrarSelectorAcorde();
}

function posicionarSelector(el) {
    const rect = el.getBoundingClientRect();
    const sw = selectorNota.offsetWidth  || 264;
    const sh = selectorNota.offsetHeight || 300;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Preferir a la derecha del elemento
    let left = rect.right + 10;
    let top  = rect.top;

    if (left + sw > vw - 8) left = rect.left - sw - 10;
    if (top + sh > vh - 8)  top  = vh - sh - 8;
    if (top < 80)            top  = 80;  // no tapar la cabecera
    if (left < 8)            left = 8;

    selectorNota.style.left = left + 'px';
    selectorNota.style.top  = top  + 'px';
}

function clicFueraSelectorHandler(e) {
    const selectorAcorde = $('selector-acorde');
    const dentroSimple = selectorNota.contains(e.target);
    const dentroAcorde = selectorAcorde && selectorAcorde.contains(e.target);
    if (!dentroSimple && !dentroAcorde) {
        cerrarSelector();
    } else {
        document.addEventListener('pointerdown', clicFueraSelectorHandler, { capture: true, once: true });
    }
}

function actualizarUISelector() {
    const { nota, alt } = estado.notaSelTmp;
    selectorNota.querySelectorAll('.btn-nota').forEach(b => {
        b.classList.toggle('activo', b.dataset.nota === nota);
    });
    const altSimple = alt === 'bb' ? 'b' : alt === '##' ? '#' : alt;
    selectorNota.querySelectorAll('.btn-alt').forEach(b => {
        b.classList.toggle('activo', b.dataset.alt === altSimple);
    });
    // «Cambiar nota» solo se activa si lo elegido es distinto de lo que pone ahora
    const el = document.querySelector(`.nota-nombre[data-id="${estado.notaActiva}"]`);
    const textoActual = el ? el.dataset.texto : null;
    const elegido = nota ? construirTextoNota(nota, alt) : null;
    const btnCambiar = $('btn-cambiar-nota');
    btnCambiar.disabled = !elegido || elegido === textoActual;
    btnCambiar.textContent = btnCambiar.disabled ? 'Cambiar nota' : `Cambiar nota a ${elegido}`;
}

function actualizarUITam() {
    const id = estado.notaActiva;
    if (id == null) return;
    const tam = obtenerTamActual(id);
    const tamStr = Number.isInteger(tam * 2) ? tam.toFixed(1).replace('.', ',') : tam.toFixed(1).replace('.', ',');
    $('selector-tam-val').textContent = tamStr + ' pt';
}

// Botones de nota
$('notas-btns').querySelectorAll('.btn-nota').forEach(btn => {
    btn.addEventListener('click', () => {
        estado.notaSelTmp.nota = btn.dataset.nota;
        actualizarUISelector();
    });
});

// Botones de alteración
selectorNota.querySelectorAll('.btn-alt').forEach(btn => {
    btn.addEventListener('click', () => {
        estado.notaSelTmp.alt = btn.dataset.alt;
        actualizarUISelector();
    });
});

// A− / A+
$('btn-tam-menos').addEventListener('click', () => {
    const id = estado.notaActiva;
    if (id == null) return;
    const tamActual = obtenerTamActual(id);
    const nuevoTam = Math.max(TAM_MIN, Math.round((tamActual - TAM_PASO) * 10) / 10);
    if (nuevoTam !== tamActual) {
        registrarHistorial(id, { tam: tamActual }, { tam: nuevoTam });
        aplicarCorreccionTam(id, nuevoTam, true);
        actualizarUITam();
        programarRecolocar();
    }
});

$('btn-tam-mas').addEventListener('click', () => {
    const id = estado.notaActiva;
    if (id == null) return;
    const tamActual = obtenerTamActual(id);
    const nuevoTam = Math.min(TAM_MAX, Math.round((tamActual + TAM_PASO) * 10) / 10);
    if (nuevoTam !== tamActual) {
        registrarHistorial(id, { tam: tamActual }, { tam: nuevoTam });
        aplicarCorreccionTam(id, nuevoTam, true);
        actualizarUITam();
        programarRecolocar();
    }
});

// Restablecer posición y tamaño
$('btn-restablecer-pos').addEventListener('click', () => {
    const id = estado.notaActiva;
    if (id == null) return;
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    if (!el) return;

    const xOrig    = Number(el.dataset.xOrig);
    const baseOrig = Number(el.dataset.baseOrig);
    const tamOrig  = Number(el.dataset.tamOrig);
    const x        = Number(el.dataset.x);
    const base     = Number(el.dataset.base);
    const tam      = Number(el.dataset.tam);

    if (xOrig !== x || baseOrig !== base || tamOrig !== tam) {
        registrarHistorial(id,
            { x, base, tam },
            { x: xOrig, base: baseOrig, tam: tamOrig }
        );
        el.dataset.x    = xOrig;
        el.dataset.base = baseOrig;
        el.dataset.tam  = tamOrig;

        // Quitar correcciones de posición/tamaño
        const corr = estado.correcciones[id] || {};
        delete corr.x;
        delete corr.base;
        delete corr.tam;
        delete corr.fija;
        if (Object.keys(corr).length === 0) {
            delete estado.correcciones[id];
        } else {
            estado.correcciones[id] = corr;
        }

        const env = el.closest('.pagina-envoltorio');
        if (env) reposicionarNotasPagina(env);
        actualizarUITam();
        programarRecolocar();
    }
    cerrarSelector();
});

// Aplicar nota seleccionada
function aplicarNotaActiva() {
    const id = estado.notaActiva;
    if (id == null) return;
    const texto = construirTextoNota(estado.notaSelTmp.nota, estado.notaSelTmp.alt);
    aplicarCorreccionTexto(id, texto);
    cerrarSelector();
    avanzarSiguienteDudosa(id);
}

$('btn-cambiar-nota').addEventListener('click', aplicarNotaActiva);

$('btn-ligada').addEventListener('click', () => {
    const id = estado.notaActiva;
    if (id == null) return;
    aplicarCorreccionTexto(id, '«·»');
    cerrarSelector();
    avanzarSiguienteDudosa(id);
});

$('btn-aceptar-prop').addEventListener('click', () => {
    const id = estado.notaActiva;
    if (id == null) return;
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    const textoOrig = el ? (el.dataset.textoOrig || el.dataset.texto) : null;
    if (textoOrig) aplicarCorreccionTexto(id, textoOrig);
    cerrarSelector();
    avanzarSiguienteDudosa(id);
});

function avanzarSiguienteDudosa(idActual) {
    const pendientes = estado.dudosaIds.filter(id => !_acordeConfirmado(id));
    if (pendientes.length === 0) return;

    const idxActual = estado.dudosaIds.indexOf(idActual);
    const idxSig = estado.dudosaIds.findIndex(
        (id, i) => i > idxActual && !_acordeConfirmado(id)
    );
    const sigId = idxSig >= 0
        ? estado.dudosaIds[idxSig]
        : pendientes[0];

    if (!sigId) return;
    estado.notaActualIdx = estado.dudosaIds.indexOf(sigId);
    actualizarNavDudosas();
    setTimeout(() => { irANota(sigId); abrirSelector(sigId); }, 80);
}

// Teclado en el selector
function teclaSelector(e) {
    if (!selectorNota.classList.contains('visible')) return;

    if (e.key === 'Escape') {
        cerrarSelector(); e.preventDefault();
    } else if (e.key === 'Enter') {
        aplicarNotaActiva(); e.preventDefault();
    } else {
        const mapa = { d: 'Do', r: 'Re', m: 'Mi', f: 'Fa', s: 'Sol', l: 'La', i: 'Si' };
        const n = mapa[e.key.toLowerCase()];
        if (n) { estado.notaSelTmp.nota = n; actualizarUISelector(); e.preventDefault(); }
    }
}

// ============================================================
// Selector de acorde
// ============================================================

const selectorAcordeEl = $('selector-acorde');

function abrirSelectorAcorde(acordeId) {
    cerrarSelectorAcorde();
    selectorNota.classList.remove('visible');

    const notas = estado.resultado ? (estado.resultado.notas || []) : [];
    const ids = estado.acordeMap[acordeId] || [];
    if (ids.length === 0) return;

    estado.acordeActivo = acordeId;

    // Inicializar estado temporal: texto actual de cada nota
    estado.acordeSelTmp = ids.map(nid => {
        const corr = estado.correcciones[nid];
        const textoActual = (corr && 'texto' in corr)
            ? corr.texto
            : (notas.find(n => n.id === nid)?.texto || '?');
        return parsearTextoNota(textoActual);
    });

    // Construir filas dinámicas
    $('acorde-titulo-n').textContent = `de ${ids.length} notas`;
    const filas = $('acorde-filas');
    filas.innerHTML = '';
    ids.forEach((nid, idx) => {
        filas.appendChild(_crearFilaAcorde(nid, idx, acordeId, notas));
    });

    // Tamaño: usar el tam de la primera nota del acorde
    _actualizarUITamAcorde(ids[0]);

    // Posicionar junto al primer elemento del acorde
    const elRep = document.querySelector(`.nota-nombre[data-id="${ids[0]}"]`);
    if (elRep) _posicionarSelectorAcorde(elRep);

    selectorAcordeEl.classList.add('visible');
    document.addEventListener('pointerdown', clicFueraSelectorHandler, { capture: true, once: true });
}

function _crearFilaAcorde(nid, idx, acordeId, notas) {
    const nota = notas.find(n => n.id === nid);
    const textoOrig = nota ? nota.texto : '?';

    const fila = document.createElement('div');
    fila.className = 'acorde-fila';
    fila.dataset.idx = idx;

    // Etiqueta con texto original
    const label = document.createElement('span');
    label.className = 'acorde-fila-label';
    label.title = 'Propuesta: ' + textoOrig;
    label.textContent = textoOrig;
    fila.appendChild(label);

    // Botones de nota (compactos)
    const notasBtns = document.createElement('div');
    notasBtns.className = 'acorde-notas-btns';
    NOTAS.forEach(nombre => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn-nota btn-nota-compacto';
        btn.dataset.nota = nombre;
        btn.textContent = nombre;
        btn.classList.toggle('activo', estado.acordeSelTmp[idx].nota === nombre);
        btn.addEventListener('click', () => {
            estado.acordeSelTmp[idx].nota = nombre;
            _actualizarUIFilaAcorde(fila, idx);
            _resaltarCabezaAcorde(nid);
        });
        notasBtns.appendChild(btn);
    });
    fila.appendChild(notasBtns);

    // Botones de alteración (compactos)
    const altBtns = document.createElement('div');
    altBtns.className = 'acorde-alt-btns';
    [['b', '♭'], ['', '♮'], ['#', '♯']].forEach(([alt, label2]) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn-alt btn-alt-compacto';
        btn.dataset.alt = alt;
        btn.setAttribute('aria-label', alt || 'Natural');
        btn.textContent = label2;
        btn.classList.toggle('activo', estado.acordeSelTmp[idx].alt === alt);
        btn.addEventListener('click', () => {
            estado.acordeSelTmp[idx].alt = alt;
            _actualizarUIFilaAcorde(fila, idx);
            _resaltarCabezaAcorde(nid);
        });
        altBtns.appendChild(btn);
    });
    // Botón ligada
    const btnLigada = document.createElement('button');
    btnLigada.type = 'button';
    btnLigada.className = 'btn-alt btn-alt-compacto';
    btnLigada.dataset.alt = '·';
    btnLigada.textContent = '·';
    btnLigada.title = 'Ligada';
    btnLigada.classList.toggle('activo', estado.acordeSelTmp[idx].nota === '·');
    btnLigada.addEventListener('click', () => {
        estado.acordeSelTmp[idx] = { nota: '·', alt: '' };
        _actualizarUIFilaAcorde(fila, idx);
        _resaltarCabezaAcorde(nid);
    });
    altBtns.appendChild(btnLigada);
    fila.appendChild(altBtns);

    // Eventos hover: resaltar notehead
    fila.addEventListener('pointerenter', () => _resaltarCabezaAcorde(nid));

    return fila;
}

function _actualizarUIFilaAcorde(fila, idx) {
    const { nota, alt } = estado.acordeSelTmp[idx];
    fila.querySelectorAll('.btn-nota-compacto').forEach(b => {
        b.classList.toggle('activo', b.dataset.nota === nota);
    });
    const altSimple = alt === 'bb' ? 'b' : alt === '##' ? '#' : alt;
    fila.querySelectorAll('.btn-alt-compacto').forEach(b => {
        if (b.dataset.alt === '·') {
            b.classList.toggle('activo', nota === '·');
        } else {
            b.classList.toggle('activo', b.dataset.alt === altSimple);
        }
    });
}

function _resaltarCabezaAcorde(nid) {
    // Quitar rings previos del acorde
    document.querySelectorAll('.cabeza-ring.ring-acorde').forEach(r => r.remove());
    const el = document.querySelector(`.nota-nombre[data-id="${nid}"]`);
    if (!el) return;
    const overlay = el.closest('.notas-overlay');
    const env     = el.closest('.pagina-envoltorio');
    if (!overlay || !env) return;
    const img = env.querySelector('.pagina-img');
    const s   = img.clientWidth / Number(env.dataset.anchoPoints);
    const cabeza = JSON.parse(el.dataset.cabeza || '[]');
    if (cabeza.length !== 4) return;
    const ring = document.createElement('div');
    ring.className = 'cabeza-ring ring-acorde';
    ring.dataset.cabeza = el.dataset.cabeza;
    actualizarRing(ring, s);
    overlay.appendChild(ring);
}

function _actualizarUITamAcorde(id) {
    const tam = obtenerTamActual(id);
    const tamStr = tam.toFixed(1).replace('.', ',');
    $('acorde-tam-val').textContent = tamStr + ' pt';
}

function _posicionarSelectorAcorde(el) {
    const rect = el.getBoundingClientRect();
    const sw = selectorAcordeEl.offsetWidth  || 400;
    const sh = selectorAcordeEl.offsetHeight || 360;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = rect.right + 10;
    let top  = rect.top;
    if (left + sw > vw - 8) left = rect.left - sw - 10;
    if (top + sh > vh - 8)  top  = vh - sh - 8;
    if (top < 80)            top  = 80;
    if (left < 8)            left = 8;
    selectorAcordeEl.style.left = left + 'px';
    selectorAcordeEl.style.top  = top  + 'px';
}

function cerrarSelectorAcorde() {
    if (!selectorAcordeEl) return;
    selectorAcordeEl.classList.remove('visible');
    document.querySelectorAll('.cabeza-ring.ring-acorde').forEach(r => r.remove());
    estado.acordeActivo = null;
}

function aplicarCorreccionAcorde() {
    const acordeId = estado.acordeActivo;
    if (acordeId == null) return;
    const ids = estado.acordeMap[acordeId] || [];
    const notas = estado.resultado ? (estado.resultado.notas || []) : [];

    // Construir lista de antes/despues para historial único
    const entradas = ids.map((nid, idx) => {
        const el = document.querySelector(`.nota-nombre[data-id="${nid}"]`);
        const antes = { texto: el ? el.dataset.texto : '' };
        const textoNuevo = construirTextoNota(estado.acordeSelTmp[idx].nota, estado.acordeSelTmp[idx].alt);
        return { id: String(nid), antes, despues: { texto: textoNuevo } };
    });

    // Registrar como UN único paso en el historial
    estado.historial.push({ esAcorde: true, entradas });
    estado.redoStack = [];
    actualizarBtnDeshacer();

    // Aplicar cada corrección
    entradas.forEach(({ id: nid, despues }) => {
        const texto = despues.texto;
        const el = document.querySelector(`.nota-nombre[data-id="${nid}"]`);
        if (el) {
            el.textContent = texto;
            el.dataset.texto = texto;
            el.classList.remove('estado-dudosa', 'estado-deducida');
            el.classList.add('estado-confirmada');
        }
        const corr = estado.correcciones[nid] || {};
        corr.texto = texto;
        estado.correcciones[nid] = corr;
        // Actualizar item de lista (representante del acorde)
        const repId = (estado.acordeMap[acordeId] || [])[0];
        actualizarItemDudosa(repId, texto);
    });

    actualizarContador();
    cerrarSelectorAcorde();
    avanzarSiguienteDudosa(ids[0]);
}

function aceptarPropuestaAcorde() {
    const acordeId = estado.acordeActivo;
    if (acordeId == null) return;
    const ids = estado.acordeMap[acordeId] || [];
    const notas = estado.resultado ? (estado.resultado.notas || []) : [];

    // Restaurar texto original de cada nota
    const entradas = ids.map(nid => {
        const el = document.querySelector(`.nota-nombre[data-id="${nid}"]`);
        const notaData = notas.find(n => n.id === nid);
        const textoOrig = notaData ? notaData.texto : (el ? el.dataset.textoOrig : '?');
        const antes = { texto: el ? el.dataset.texto : '' };
        return { id: String(nid), antes, despues: { texto: textoOrig } };
    });

    estado.historial.push({ esAcorde: true, entradas });
    estado.redoStack = [];
    actualizarBtnDeshacer();

    entradas.forEach(({ id: nid, despues }) => {
        const texto = despues.texto;
        const el = document.querySelector(`.nota-nombre[data-id="${nid}"]`);
        if (el) {
            el.textContent = texto;
            el.dataset.texto = texto;
            el.classList.remove('estado-dudosa', 'estado-deducida');
            el.classList.add('estado-confirmada');
        }
        const corr = estado.correcciones[nid] || {};
        corr.texto = texto;
        estado.correcciones[nid] = corr;
    });
    const repId = (estado.acordeMap[acordeId] || [])[0];
    actualizarItemDudosa(repId, '');
    actualizarContador();
    cerrarSelectorAcorde();
    avanzarSiguienteDudosa(ids[0]);
}

// Conectar botones del selector de acorde
$('acorde-btn-aplicar').addEventListener('click', aplicarCorreccionAcorde);
$('acorde-btn-aceptar').addEventListener('click', aceptarPropuestaAcorde);

$('acorde-tam-menos').addEventListener('click', () => {
    const acordeId = estado.acordeActivo;
    if (acordeId == null) return;
    const ids = estado.acordeMap[acordeId] || [];
    ids.forEach(nid => {
        const tamActual = obtenerTamActual(nid);
        const nuevoTam = Math.max(TAM_MIN, Math.round((tamActual - TAM_PASO) * 10) / 10);
        if (nuevoTam !== tamActual) aplicarCorreccionTam(nid, nuevoTam, true);
    });
    if (ids.length) _actualizarUITamAcorde(ids[0]);
    programarRecolocar();
});

$('acorde-tam-mas').addEventListener('click', () => {
    const acordeId = estado.acordeActivo;
    if (acordeId == null) return;
    const ids = estado.acordeMap[acordeId] || [];
    ids.forEach(nid => {
        const tamActual = obtenerTamActual(nid);
        const nuevoTam = Math.min(TAM_MAX, Math.round((tamActual + TAM_PASO) * 10) / 10);
        if (nuevoTam !== tamActual) aplicarCorreccionTam(nid, nuevoTam, true);
    });
    if (ids.length) _actualizarUITamAcorde(ids[0]);
    programarRecolocar();
});

$('acorde-btn-restablecer').addEventListener('click', () => {
    const acordeId = estado.acordeActivo;
    if (acordeId == null) return;
    const ids = estado.acordeMap[acordeId] || [];
    ids.forEach(nid => {
        const el = document.querySelector(`.nota-nombre[data-id="${nid}"]`);
        if (!el) return;
        el.dataset.x    = el.dataset.xOrig;
        el.dataset.base = el.dataset.baseOrig;
        el.dataset.tam  = el.dataset.tamOrig;
        const corr = estado.correcciones[nid] || {};
        delete corr.x; delete corr.base; delete corr.tam; delete corr.fija;
        if (Object.keys(corr).length === 0) delete estado.correcciones[nid];
        else estado.correcciones[nid] = corr;
        const env = el.closest('.pagina-envoltorio');
        if (env) reposicionarNotasPagina(env);
    });
    if (ids.length) _actualizarUITamAcorde(ids[0]);
    programarRecolocar();
    cerrarSelectorAcorde();
});

// ============================================================
// Teclado global (paso revisar)
// ============================================================

document.addEventListener('keydown', e => {
    // Solo activo en el paso revisar y si el selector está cerrado
    const enRevisar = $('paso-revisar') && $('paso-revisar').classList.contains('activo');
    if (!enRevisar) return;
    const selectorAcorde = $('selector-acorde');
    if (selectorNota.classList.contains('visible')) return;
    if (selectorAcorde && selectorAcorde.classList.contains('visible')) return;

    // Ctrl+Z / Ctrl+Y
    if (e.ctrlKey && e.key === 'z') {
        deshacer(); e.preventDefault(); return;
    }
    if (e.ctrlKey && (e.key === 'y' || (e.shiftKey && e.key === 'Z'))) {
        rehacer(); e.preventDefault(); return;
    }

    const id = estado.notaSeleccionadaId;

    // Navegación: N/P o Tab/Shift+Tab
    if (e.key === 'n' || e.key === 'N' || (e.key === 'Tab' && !e.shiftKey)) {
        navegarDudosa(1); e.preventDefault(); return;
    }
    if (e.key === 'p' || e.key === 'P' || (e.key === 'Tab' && e.shiftKey)) {
        navegarDudosa(-1); e.preventDefault(); return;
    }

    // Flechas: nudge de 0.5 pt (Shift: 2 pt)
    if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) {
        if (!id) return;
        e.preventDefault();
        const paso = e.shiftKey ? 2 : 0.5;
        const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
        if (!el) return;
        const x    = Number(el.dataset.x);
        const base = Number(el.dataset.base);
        const tam  = Number(el.dataset.tam);
        let nx = x, nb = base;
        if (e.key === 'ArrowLeft')  nx   -= paso;
        if (e.key === 'ArrowRight') nx   += paso;
        if (e.key === 'ArrowUp')    nb   -= paso;
        if (e.key === 'ArrowDown')  nb   += paso;
        registrarHistorial(id, { x, base }, { x: nx, base: nb });
        aplicarCorreccionPosicion(id, nx, nb, tam, true);
        moverHandle(el);
        programarRecolocar();
        return;
    }
});

// ============================================================
// Confirmar y generar PDF
// ============================================================

$('btn-confirmar').addEventListener('click', () => {
    const pendientes = estado.dudosaIds.filter(id => {
        const corr = estado.correcciones[id];
        return !corr || !('texto' in corr);
    }).length;
    if (pendientes > 0) {
        const msg = pendientes === 1
            ? 'Queda 1 nota sin revisar; se guardará con la propuesta original. ¿Continuar?'
            : `Quedan ${pendientes} notas sin revisar; se guardarán con la propuesta original. ¿Continuar?`;
        $('modal-mensaje').textContent = msg;
        modalFondo.classList.add('visible');
    } else {
        ejecutarConfirmar();
    }
});

$('modal-cancelar').addEventListener('click',  () => modalFondo.classList.remove('visible'));
$('modal-continuar').addEventListener('click', () => { modalFondo.classList.remove('visible'); ejecutarConfirmar(); });
modalFondo.addEventListener('click', e => { if (e.target === modalFondo) modalFondo.classList.remove('visible'); });

function ejecutarConfirmar() {
    $('btn-confirmar').disabled = true;
    $('btn-confirmar').textContent = 'Generando PDF…';

    // Construir correcciones con datos actuales del DOM
    const corrParaEnviar = {};
    document.querySelectorAll('.nota-nombre').forEach(el => {
        const id   = el.dataset.id;
        const base = estado.correcciones[id] || {};
        const obj  = Object.assign({}, base);
        obj.x    = Number(el.dataset.x);
        obj.base = Number(el.dataset.base);
        obj.tam  = Number(el.dataset.tam);
        if (obj.x !== Number(el.dataset.xOrig) || obj.base !== Number(el.dataset.baseOrig) || obj.tam !== Number(el.dataset.tamOrig)) {
            obj.fija = true;
        }
        corrParaEnviar[id] = obj;
    });

    fetch(`/api/trabajos/${estado.idTrabajo}/confirmar`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ correcciones: corrParaEnviar }),
    })
    .then(r => r.json())
    .then(d => {
        $('btn-confirmar').disabled = false;
        $('btn-confirmar').textContent = 'Confirmar y descargar PDF';
        if (d.error) { alert('Error al generar el PDF: ' + d.error); return; }
        estado.descargaUrl    = d.descarga;
        estado.descargaNombre = d.nombre;
        mostrarPasoListo(d.descarga, d.nombre, 'nombres');
    })
    .catch(err => {
        $('btn-confirmar').disabled = false;
        $('btn-confirmar').textContent = 'Confirmar y descargar PDF';
        alert('Error: ' + err.message);
    });
}

// ============================================================
// Paso LISTO
// ============================================================

function mostrarPasoListo(descargaUrl, nombreArchivo, flujo) {
    $('listo-nombre').textContent = nombreArchivo;
    actualizarIndicador(flujo === 'empalme' ? 'listo-empalme' : 'listo');
    mostrarSeccion('listo');

    const enPywebview  = typeof window.pywebview !== 'undefined';
    const btnGuardar   = $('btn-guardar-pdf');
    const btnDescargar = $('btn-descargar-pdf');
    const btnAbrir     = $('btn-abrir-pdf');

    if (enPywebview) {
        btnGuardar.style.display   = '';
        btnDescargar.style.display = 'none';
        btnAbrir.style.display     = '';
    } else {
        btnGuardar.style.display   = 'none';
        btnDescargar.style.display = '';
        btnDescargar.href          = descargaUrl;
        btnDescargar.download      = nombreArchivo;
        btnAbrir.style.display     = 'none';
    }
}

$('btn-guardar-pdf').addEventListener('click', () => {
    if (typeof window.pywebview !== 'undefined') {
        window.pywebview.api.guardar_pdf(estado.idTrabajo)
            .catch(err => console.error('guardar_pdf error:', err));
    }
});

$('btn-abrir-pdf').addEventListener('click', () => {
    if (typeof window.pywebview !== 'undefined') {
        window.pywebview.api.abrir_pdf(estado.idTrabajo)
            .catch(err => console.error('abrir_pdf error:', err));
    }
});

$('btn-nueva-partitura').addEventListener('click', () => {
    reiniciar();
    mostrarSeccion('inicio');
});

function reiniciar() {
    if (estado.intervaloPoll) clearInterval(estado.intervaloPoll);
    estado.idTrabajo        = null;
    estado.resultado        = null;
    estado.correcciones     = {};
    estado.historial        = [];
    estado.redoStack        = [];
    estado.dudosaIds        = [];
    estado.notaActualIdx    = 0;
    estado.notaSeleccionadaId = null;
    estado.descargaUrl      = null;
    estado.descargaNombre   = null;
    estado.archivosEmpalme  = [];
    estado.empalmeDescargaUrl = null;
    estado.empalmeDescargaNombre = null;
    scrollPags.innerHTML = '';
    cerrarSelector();
    quitarHandle();
    mostrarEstadoCarga('carga');
    actualizarBtnDeshacer();
}

// ============================================================
// EMPALME — Subir y ordenar PDFs
// ============================================================

const zonaCargaEmpalme = $('zona-carga-empalme');
const inputEmpalme     = $('input-empalme');
const inputEmpalmesMas = $('input-empalme-mas');

// Drag & drop en zona de empalme
zonaCargaEmpalme.addEventListener('dragover', e => { e.preventDefault(); zonaCargaEmpalme.classList.add('arrastrando'); });
zonaCargaEmpalme.addEventListener('dragleave', () => zonaCargaEmpalme.classList.remove('arrastrando'));
zonaCargaEmpalme.addEventListener('drop', e => {
    e.preventDefault();
    zonaCargaEmpalme.classList.remove('arrastrando');
    subirArchivosEmpalme(Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf')));
});
zonaCargaEmpalme.addEventListener('click', () => inputEmpalme.click());
zonaCargaEmpalme.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') inputEmpalme.click(); });
$('btn-elegir-empalme').addEventListener('click', e => { e.stopPropagation(); inputEmpalme.click(); });

inputEmpalme.addEventListener('change', () => {
    if (inputEmpalme.files.length) subirArchivosEmpalme(Array.from(inputEmpalme.files));
    inputEmpalme.value = '';
});

$('btn-anyadir-mas').addEventListener('click', e => {
    e.stopPropagation();
    inputEmpalmesMas.click();
});
inputEmpalmesMas.addEventListener('change', () => {
    if (inputEmpalmesMas.files.length) subirArchivosEmpalme(Array.from(inputEmpalmesMas.files));
    inputEmpalmesMas.value = '';
});

async function subirArchivosEmpalme(archivos) {
    if (!archivos.length) return;

    // Mostrar la lista si hay al menos uno
    $('zona-carga-empalme').style.display = 'none';
    $('empalme-lista-wrap').style.display = '';
    $('empalme-hint').style.display = estado.archivosEmpalme.length + archivos.length < 2 ? '' : 'none';
    $('btn-unir').disabled = true;

    for (const arch of archivos) {
        if (!arch.name.toLowerCase().endsWith('.pdf')) continue;
        try {
            const r = await fetch('/api/empalme/archivos', {
                method: 'POST',
                headers: { 'X-Nombre-Archivo': encodeURIComponent(arch.name) },
                body: arch,
            });
            const d = await r.json();
            if (d.error) { console.error('empalme subida error:', d.error); continue; }

            // Aviso de duplicado por SHA-256
            const dup = estado.archivosEmpalme.find(a => a.sha256 === d.sha256);
            if (dup) {
                mostrarAvisoEmpalme(`«${d.titulo}» parece idéntico a «${dup.titulo}» (mismo contenido).`);
            }

            estado.archivosEmpalme.push(d);
        } catch (err) {
            console.error('Error al subir', arch.name, err);
        }
    }

    renderizarListaEmpalme();
    actualizarBtnUnir();
}

function mostrarAvisoEmpalme(msg) {
    const av = $('empalme-aviso');
    $('empalme-aviso-texto').textContent = msg;
    av.style.display = '';
    setTimeout(() => { av.style.display = 'none'; }, 6000);
}

function renderizarListaEmpalme() {
    const lista = $('empalme-lista');
    lista.innerHTML = '';
    estado.archivosEmpalme.forEach((a, idx) => {
        lista.appendChild(crearItemEmpalme(a, idx));
    });
}

function crearItemEmpalme(a, idx) {
    const li = document.createElement('li');
    li.className = 'empalme-item';
    li.dataset.id = a.id;
    li.dataset.idx = idx;
    li.draggable = true;

    // Handle ⠿
    const handle = document.createElement('span');
    handle.className = 'empalme-handle';
    handle.textContent = '⠿';
    handle.title = 'Arrastrar para reordenar';

    // Número de orden
    const orden = document.createElement('span');
    orden.className = 'empalme-orden';
    orden.textContent = idx + 1;

    // Miniatura
    const mini = document.createElement('img');
    mini.className = 'empalme-miniatura';
    mini.src = a.miniatura;
    mini.alt = 'Página 1';
    mini.title = 'Ver miniatura';
    mini.addEventListener('click', () => mostrarModalMiniatura(a.miniatura));

    // Info
    const info = document.createElement('div');
    info.className = 'empalme-info';

    const tituloInput = document.createElement('input');
    tituloInput.type = 'text';
    tituloInput.className = 'empalme-titulo-input';
    tituloInput.value = a.titulo;
    tituloInput.addEventListener('change', () => { a.titulo = tituloInput.value; });

    const meta = document.createElement('div');
    meta.className = 'empalme-meta';
    meta.textContent = `${a.archivo} · ${a.paginas} pág.`;

    info.appendChild(tituloInput);
    info.appendChild(meta);

    // Controles ↑ ↓
    const controles = document.createElement('div');
    controles.className = 'empalme-controles';
    const btnUp = document.createElement('button');
    btnUp.textContent = '↑';
    btnUp.title = 'Subir';
    btnUp.disabled = idx === 0;
    btnUp.addEventListener('click', () => {
        if (idx === 0) return;
        [estado.archivosEmpalme[idx - 1], estado.archivosEmpalme[idx]] =
         [estado.archivosEmpalme[idx], estado.archivosEmpalme[idx - 1]];
        renderizarListaEmpalme();
    });
    const btnDown = document.createElement('button');
    btnDown.textContent = '↓';
    btnDown.title = 'Bajar';
    btnDown.disabled = idx === estado.archivosEmpalme.length - 1;
    btnDown.addEventListener('click', () => {
        if (idx === estado.archivosEmpalme.length - 1) return;
        [estado.archivosEmpalme[idx], estado.archivosEmpalme[idx + 1]] =
         [estado.archivosEmpalme[idx + 1], estado.archivosEmpalme[idx]];
        renderizarListaEmpalme();
    });
    controles.appendChild(btnUp);
    controles.appendChild(btnDown);

    // Quitar ✕
    const btnQuitar = document.createElement('button');
    btnQuitar.className = 'empalme-quitar';
    btnQuitar.textContent = '✕';
    btnQuitar.title = 'Quitar';
    btnQuitar.addEventListener('click', () => {
        estado.archivosEmpalme.splice(idx, 1);
        renderizarListaEmpalme();
        actualizarBtnUnir();
        if (estado.archivosEmpalme.length === 0) {
            $('zona-carga-empalme').style.display = '';
            $('empalme-lista-wrap').style.display = 'none';
        }
    });

    li.appendChild(handle);
    li.appendChild(orden);
    li.appendChild(mini);
    li.appendChild(info);
    li.appendChild(controles);
    li.appendChild(btnQuitar);

    // Drag-to-reorder HTML5
    let draggingIdx = null;
    li.addEventListener('dragstart', e => {
        draggingIdx = idx;
        li.classList.add('arrastrado');
        e.dataTransfer.effectAllowed = 'move';
    });
    li.addEventListener('dragend', () => { li.classList.remove('arrastrado'); draggingIdx = null; });
    li.addEventListener('dragover', e => {
        e.preventDefault();
        li.classList.add('sobre');
    });
    li.addEventListener('dragleave', () => li.classList.remove('sobre'));
    li.addEventListener('drop', e => {
        e.preventDefault();
        li.classList.remove('sobre');
        if (draggingIdx != null && draggingIdx !== idx) {
            const [item] = estado.archivosEmpalme.splice(draggingIdx, 1);
            estado.archivosEmpalme.splice(idx, 0, item);
            renderizarListaEmpalme();
        }
    });

    return li;
}

function actualizarBtnUnir() {
    const n = estado.archivosEmpalme.length;
    $('btn-unir').disabled = n < 2;
    $('empalme-hint').style.display = n < 2 && n > 0 ? '' : 'none';
}

// Nombre del archivo resultante
$('empalme-nombre-archivo').addEventListener('input', () => {});

// Unir y descargar
$('btn-unir').addEventListener('click', () => {
    if (estado.archivosEmpalme.length < 2) return;
    const nombre = $('empalme-nombre-archivo').value.trim() || 'Marchas empalmadas';

    $('empalme-lista-wrap').style.display  = 'none';
    $('empalme-procesando').style.display  = '';

    fetch('/api/empalme/unir', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
            ids:    estado.archivosEmpalme.map(a => a.id),
            nombre: nombre,
        }),
    })
    .then(r => r.json())
    .then(d => {
        $('empalme-procesando').style.display = 'none';
        if (d.error) { alert('Error al unir: ' + d.error); $('empalme-lista-wrap').style.display = ''; return; }
        estado.empalmeDescargaUrl   = d.descarga;
        estado.empalmeDescargaNombre = d.nombre;
        mostrarPasoListo(d.descarga, d.nombre, 'empalme');
    })
    .catch(err => {
        $('empalme-procesando').style.display = 'none';
        $('empalme-lista-wrap').style.display = '';
        alert('Error: ' + err.message);
    });
});

// Modal de miniatura
function mostrarModalMiniatura(src) {
    $('modal-miniatura-img').src = src;
    $('modal-miniatura').classList.add('visible');
}
$('modal-miniatura-cerrar').addEventListener('click', () => $('modal-miniatura').classList.remove('visible'));
$('modal-miniatura').addEventListener('click', e => {
    if (e.target === $('modal-miniatura') || e.target === $('modal-miniatura-contenido')) {
        $('modal-miniatura').classList.remove('visible');
    }
});

// ============================================================
// Cierre del documento
// ============================================================
window.addEventListener('beforeunload', () => {
    if (estado.intervaloPoll) clearInterval(estado.intervaloPoll);
    if (estado._timerRecolocar) clearTimeout(estado._timerRecolocar);
});
