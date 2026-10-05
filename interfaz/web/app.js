/**
 * app.js — Lógica de la interfaz de pdf2notas
 * Agrupación Musical Stmo. Cristo de la Salud — Alcalá la Real
 */

'use strict';

// ============================================================
// Constante: nombre de la aplicación
// ============================================================
const NOMBRE_APP = 'pdf2notas';
document.title = NOMBRE_APP;

// ============================================================
// Estado global
// ============================================================
const estado = {
    paso: 1,
    idTrabajo: null,
    intervaloPoll: null,
    resultado: null,
    descargaUrl: null,
    descargaNombre: null,
    // Selector de nota
    notaActiva: null,      // id de la nota con el popover abierto
    notaActualIdx: 0,      // índice en dudosaIds
    dudosaIds: [],         // ids de las notas dudosas/deducidas, en orden de aparición
    correciones: {},       // {id: texto} – lo que el usuario ha cambiado
    notaSelTmp: { nota: null, alt: '' }, // selección temporal en el popover
    // Zoom
    zoom: 1.0,
    anchoBaseRef: null,    // ancho natural de la primera página
};

// ============================================================
// Referencias DOM
// ============================================================
const $ = id => document.getElementById(id);
const pasosDOM   = document.querySelectorAll('.paso');
const indPasos   = document.querySelectorAll('.paso-ind');
const zonaCarga  = $('zona-carga');
const inputArch  = $('input-archivo');
const faseTexto  = $('fase-texto');
const errorMsg   = $('error-mensaje');
const scrollPags = $('scroll-paginas');
const selectorNota = $('selector-nota');
const modalFondo   = $('modal-fondo');

// ============================================================
// Utilidades de paso / UI
// ============================================================

function irAPaso(n) {
    estado.paso = n;
    pasosDOM.forEach((s, i) => {
        s.classList.toggle('activo', i + 1 === n);
    });
    indPasos.forEach(ind => {
        const p = Number(ind.dataset.paso);
        ind.classList.toggle('activo', p === n);
        ind.classList.toggle('hecho', p < n);
    });
}

function mostrarEstadoCarga(nombre) {
    $('estado-carga').style.display = (nombre === 'carga') ? '' : 'none';
    $('estado-procesando').style.display = (nombre === 'procesando') ? '' : 'none';
    $('estado-error').style.display = (nombre === 'error') ? '' : 'none';
}

function mostrarError(msg) {
    errorMsg.textContent = msg;
    mostrarEstadoCarga('error');
    irAPaso(1);
}

// ============================================================
// Paso 1 — Subir archivo
// ============================================================

// Intentar precargar cabecera.jpg como fondo hero
(function() {
    const heroImg = $('hero-imagen');
    const img = new Image();
    img.onload = () => {
        heroImg.style.backgroundImage = "url('img/cabecera.jpg')";
        heroImg.style.backgroundPosition = 'center right';
        heroImg.style.backgroundSize = 'cover';
    };
    img.src = 'img/cabecera.jpg';
})();

// Drag & drop
zonaCarga.addEventListener('dragover', e => {
    e.preventDefault();
    zonaCarga.classList.add('arrastrando');
});
zonaCarga.addEventListener('dragleave', () => zonaCarga.classList.remove('arrastrando'));
zonaCarga.addEventListener('drop', e => {
    e.preventDefault();
    zonaCarga.classList.remove('arrastrando');
    const arch = e.dataTransfer.files[0];
    if (arch) procesarArchivo(arch);
});
zonaCarga.addEventListener('click', () => inputArch.click());
zonaCarga.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') inputArch.click();
});
$('btn-elegir').addEventListener('click', e => {
    e.stopPropagation();
    inputArch.click();
});
inputArch.addEventListener('change', () => {
    if (inputArch.files[0]) procesarArchivo(inputArch.files[0]);
    inputArch.value = '';
});
$('btn-reintentar').addEventListener('click', () => {
    mostrarEstadoCarga('carga');
});

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
// Paso 2 — Cargar revisión
// ============================================================

function cargarRevision(res) {
    estado.resultado = res;
    estado.correciones = {};
    estado.dudosaIds = [];

    // Calcular lista de dudosas en orden de página/posición
    const notas = res.notas || [];
    notas.forEach(n => {
        if (n.estado === 'dudosa' || n.estado === 'deducida') {
            estado.dudosaIds.push(n.id);
        }
    });
    estado.notaActualIdx = 0;

    renderizarCabeceraBanda(res);
    renderizarPaginas(res);
    actualizarContador();
    renderizarListaDudosas(notas);
    actualizarNavDudosas();

    irAPaso(2);

    // Ir a la primera nota dudosa si las hay
    if (estado.dudosaIds.length > 0) {
        setTimeout(() => irANota(estado.dudosaIds[0]), 300);
    }
}

function renderizarCabeceraBanda(res) {
    const listaCambios = $('lista-cambios');
    listaCambios.innerHTML = '';
    const cambios = res.cambios || [];
    cambios.slice(0, 6).forEach(c => {
        const li = document.createElement('li');
        li.textContent = c;
        listaCambios.appendChild(li);
    });

    const listaAvisos = $('lista-avisos');
    listaAvisos.innerHTML = '';
    const avisos = res.avisos || [];
    avisos.forEach(a => {
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

    // Calcular ancho base (en puntos) para establecer el zoom
    if (paginasInfo.length > 0) {
        estado.anchoBaseRef = paginasInfo[0].ancho;
    }

    paginasInfo.forEach((pag, idx) => {
        const notasPag = notas.filter(n => n.pagina === idx);
        const env = crearEnvolturaPagina(idx, pag, notasPag, res.nombre_archivo);
        scrollPags.appendChild(env);
        resizeObs.observe(env);
    });

    aplicarZoom(1.0);
}

function crearEnvolturaPagina(idx, pag, notas, nombreArch) {
    const env = document.createElement('div');
    env.className = 'pagina-envoltorio';
    env.dataset.paginaIdx = idx;
    env.dataset.anchoPoints = pag.ancho;
    env.dataset.altoPoints = pag.alto;

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
    el.dataset.id = nota.id;
    el.dataset.anchoPoints = pag.ancho;
    el.dataset.altoPoints = pag.alto;
    el.dataset.x = nota.x;
    el.dataset.base = nota.base;
    el.dataset.tam = nota.tam;
    el.dataset.cabeza = JSON.stringify(nota.cabeza);
    el.dataset.texto = nota.texto;
    el.dataset.textoOrig = nota.texto;
    el.dataset.estado = nota.estado;
    el.dataset.motivo = nota.motivo || '';
    el.textContent = nota.texto;

    el.addEventListener('click', e => {
        e.stopPropagation();
        abrirSelector(nota.id);
    });
    return el;
}

function reposicionarNotasPagina(env) {
    const img = env.querySelector('.pagina-img');
    if (!img.naturalWidth) return;
    const anchoPoints = Number(env.dataset.anchoPoints);
    const altoPoints  = Number(env.dataset.altoPoints);
    const s = img.clientWidth / anchoPoints;   // px por punto PDF

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

    // Reposicionar el ring de cabeza si está visible
    const ring = overlay.querySelector('.cabeza-ring');
    if (ring) actualizarRing(ring, s);
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

    const scroll = scrollPags;
    const contenedorAncho = scroll.clientWidth - 96; // con padding

    document.querySelectorAll('.pagina-envoltorio').forEach(env => {
        env.style.width = (contenedorAncho * zoom) + 'px';
    });
    reposicionarTodasLasNotas();
}

$('zoom-menos').addEventListener('click', () => {
    aplicarZoom(Math.max(0.3, estado.zoom - 0.15));
});
$('zoom-mas').addEventListener('click', () => {
    aplicarZoom(Math.min(3.0, estado.zoom + 0.15));
});
$('zoom-ajustar').addEventListener('click', () => aplicarZoom(1.0));

// ============================================================
// Barra lateral: contador y lista
// ============================================================

function actualizarContador() {
    const pendientes = estado.dudosaIds.filter(id => !estado.correciones[id]).length;
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

function renderizarListaDudosas(notas) {
    const lista = $('lista-dudosas');
    lista.innerHTML = '';
    estado.dudosaIds.forEach(id => {
        const nota = notas.find(n => n.id === id);
        if (!nota) return;
        lista.appendChild(crearItemDudosa(nota));
    });
}

function crearItemDudosa(nota) {
    const li = document.createElement('li');
    li.className = 'item-dudosa';
    li.dataset.id = nota.id;

    const loc = document.createElement('div');
    loc.className = 'item-dudosa-loc';
    const partes = [];
    if (nota.linea) partes.push(`Línea ${nota.linea}`);
    if (nota.compas) partes.push(`compás ${nota.compas}`);
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
    });
    return li;
}

function actualizarItemDudosa(id, texto) {
    const li = document.querySelector(`.item-dudosa[data-id="${id}"]`);
    if (!li) return;
    li.querySelector('.item-dudosa-nota').textContent = texto;
    if (estado.correciones[id] !== undefined) {
        li.classList.add('confirmada');
    } else {
        li.classList.remove('confirmada');
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
// Scroll a nota + highlight cabeza
// ============================================================

function irANota(id) {
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    if (!el) return;

    // Quitar selección anterior
    document.querySelectorAll('.nota-nombre.seleccionada').forEach(e => {
        e.classList.remove('seleccionada');
    });
    document.querySelectorAll('.cabeza-ring').forEach(r => r.remove());

    el.classList.add('seleccionada');

    // Añadir ring alrededor de la cabeza
    const overlay = el.closest('.notas-overlay');
    const env = el.closest('.pagina-envoltorio');
    const img = env.querySelector('.pagina-img');
    const anchoPoints = Number(env.dataset.anchoPoints);
    const s = img.clientWidth / anchoPoints;

    const cabeza = JSON.parse(el.dataset.cabeza || '[]');
    if (cabeza.length === 4) {
        const ring = document.createElement('div');
        ring.className = 'cabeza-ring';
        ring.dataset.cabeza = el.dataset.cabeza;
        actualizarRing(ring, s);
        overlay.appendChild(ring);
    }

    // Destacar en la lista lateral
    document.querySelectorAll('.item-dudosa').forEach(li => li.classList.remove('activo'));
    const liActivo = document.querySelector(`.item-dudosa[data-id="${id}"]`);
    if (liActivo) {
        liActivo.classList.add('activo');
        liActivo.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    // Scroll al nota en el área de páginas
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

// ============================================================
// Selector de nota (popover)
// ============================================================

const NOTAS = ['Do', 'Re', 'Mi', 'Fa', 'Sol', 'La', 'Si'];

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
    if (texto === '·') return { nota: '·', alt: '' };
    return { nota: '?', alt: '' };
}

function construirTextoNota(nota, alt) {
    if (nota === '·' || nota === '?') return nota;
    return nota + alt;
}

function abrirSelector(id) {
    cerrarSelector();
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    if (!el) return;

    estado.notaActiva = id;

    // Texto propuesto: lo original de Audiveris (no correciones anteriores)
    const textoOrig = el.dataset.textoOrig || el.dataset.texto;
    $('prop-texto').textContent = textoOrig;

    // Inicializar selección con el texto actual (puede ser corregido)
    const textoActual = estado.correciones[id] !== undefined
        ? estado.correciones[id] : el.dataset.texto;
    const { nota, alt } = parsearTextoNota(textoActual);
    estado.notaSelTmp = { nota, alt };
    actualizarUISelector();

    // Posicionar el popover cerca del elemento
    posicionarSelector(el);
    selectorNota.classList.add('visible');
    document.addEventListener('keydown', teclaSelector);
    document.addEventListener('click', clicFueraSelectorHandler, { capture: true, once: true });
}

function cerrarSelector() {
    selectorNota.classList.remove('visible');
    document.removeEventListener('keydown', teclaSelector);
    estado.notaActiva = null;
}

function posicionarSelector(el) {
    const rect = el.getBoundingClientRect();
    const sw = selectorNota.offsetWidth  || 264;
    const sh = selectorNota.offsetHeight || 260;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Intentar abajo-derecha
    let left = rect.right + 8;
    let top  = rect.top;

    // No salir por la derecha
    if (left + sw > vw - 8) left = rect.left - sw - 8;
    // No salir por abajo
    if (top + sh > vh - 8) top = vh - sh - 8;
    // No salir por arriba
    if (top < 8) top = 8;
    // No salir por la izquierda
    if (left < 8) left = 8;

    selectorNota.style.left = left + 'px';
    selectorNota.style.top  = top  + 'px';
}

function clicFueraSelectorHandler(e) {
    if (!selectorNota.contains(e.target)) {
        cerrarSelector();
    } else {
        // Re-registrar
        document.addEventListener('click', clicFueraSelectorHandler, { capture: true, once: true });
    }
}

function actualizarUISelector() {
    const { nota, alt } = estado.notaSelTmp;
    // Botones de nota
    selectorNota.querySelectorAll('.btn-nota').forEach(b => {
        b.classList.toggle('activo', b.dataset.nota === nota);
    });
    // Botones de alteración (mostrar solo ♭ ♮ ♯; para 'bb' y '##' se usa la propuesta)
    const altSimple = alt === 'bb' ? 'b' : alt === '##' ? '#' : alt;
    selectorNota.querySelectorAll('.btn-alt').forEach(b => {
        b.classList.toggle('activo', b.dataset.alt === altSimple);
    });
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

// Aplicar nota y cerrar
function aplicarNotaActiva() {
    const id = estado.notaActiva;
    if (id == null) return;
    const texto = construirTextoNota(estado.notaSelTmp.nota, estado.notaSelTmp.alt);
    aplicarCorreccion(id, texto);
    cerrarSelector();
    avanzarSiguienteDudosa(id);
}

$('btn-ligada').addEventListener('click', () => {
    const id = estado.notaActiva;
    if (id == null) return;
    aplicarCorreccion(id, '·');
    cerrarSelector();
    avanzarSiguienteDudosa(id);
});

$('btn-aceptar-prop').addEventListener('click', () => {
    const id = estado.notaActiva;
    if (id == null) return;
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    const textoOrig = el ? (el.dataset.textoOrig || el.dataset.texto) : null;
    if (textoOrig) {
        aplicarCorreccion(id, textoOrig);
    }
    cerrarSelector();
    avanzarSiguienteDudosa(id);
});

function aplicarCorreccion(id, texto) {
    estado.correciones[id] = texto;

    // Actualizar el elemento de overlay
    const el = document.querySelector(`.nota-nombre[data-id="${id}"]`);
    if (el) {
        el.textContent = texto;
        el.dataset.texto = texto;
        el.classList.remove('estado-dudosa', 'estado-deducida');
        el.classList.add('estado-confirmada');
    }
    // Actualizar la lista lateral
    actualizarItemDudosa(id, texto);
    actualizarContador();
}

function avanzarSiguienteDudosa(idActual) {
    const pendientes = estado.dudosaIds.filter(id => !estado.correciones[id] && id !== idActual);
    if (pendientes.length === 0) return;
    // La siguiente sin corregir después del actual
    const idxActual = estado.dudosaIds.indexOf(idActual);
    const idxSig = estado.dudosaIds.findIndex(
        (id, i) => i > idxActual && !estado.correciones[id]
    );
    const sigId = idxSig >= 0
        ? estado.dudosaIds[idxSig]
        : estado.dudosaIds.find(id => !estado.correciones[id]);
    if (!sigId) return;
    estado.notaActualIdx = estado.dudosaIds.indexOf(sigId);
    actualizarNavDudosas();
    setTimeout(() => {
        irANota(sigId);
        abrirSelector(sigId);
    }, 80);
}

// Teclado en el selector
function teclaSelector(e) {
    if (!selectorNota.classList.contains('visible')) return;

    if (e.key === 'Escape') {
        cerrarSelector();
        e.preventDefault();
    } else if (e.key === 'Enter') {
        // Aceptar propuesta
        $('btn-aceptar-prop').click();
        e.preventDefault();
    } else if (e.key === 'ArrowLeft') {
        navegarDudosa(-1);
        e.preventDefault();
    } else if (e.key === 'ArrowRight') {
        navegarDudosa(1);
        e.preventDefault();
    } else {
        // Atajos de nota: D=Do R=Re M=Mi F=Fa S=Sol L=La I=Si
        const mapa = { d: 'Do', r: 'Re', m: 'Mi', f: 'Fa', s: 'Sol', l: 'La', i: 'Si' };
        const n = mapa[e.key.toLowerCase()];
        if (n) {
            estado.notaSelTmp.nota = n;
            actualizarUISelector();
            e.preventDefault();
        }
    }
}

// ============================================================
// Confirmar y generar PDF
// ============================================================

$('btn-confirmar').addEventListener('click', () => {
    const pendientes = estado.dudosaIds.filter(id => !estado.correciones[id]).length;
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

$('modal-cancelar').addEventListener('click', () => {
    modalFondo.classList.remove('visible');
});
$('modal-continuar').addEventListener('click', () => {
    modalFondo.classList.remove('visible');
    ejecutarConfirmar();
});
modalFondo.addEventListener('click', e => {
    if (e.target === modalFondo) modalFondo.classList.remove('visible');
});

function ejecutarConfirmar() {
    // Deshabilitar el botón para evitar doble envío
    $('btn-confirmar').disabled = true;
    $('btn-confirmar').textContent = 'Generando PDF…';

    fetch(`/api/trabajos/${estado.idTrabajo}/confirmar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ correcciones: estado.correciones }),
    })
    .then(r => r.json())
    .then(d => {
        $('btn-confirmar').disabled = false;
        $('btn-confirmar').textContent = 'Confirmar y descargar PDF';
        if (d.error) { alert('Error al generar el PDF: ' + d.error); return; }
        estado.descargaUrl    = d.descarga;
        estado.descargaNombre = d.nombre;
        mostrarPasoListo(d);
    })
    .catch(err => {
        $('btn-confirmar').disabled = false;
        $('btn-confirmar').textContent = 'Confirmar y descargar PDF';
        alert('Error: ' + err.message);
    });
}

// ============================================================
// Paso 3 — Listo
// ============================================================

function mostrarPasoListo(d) {
    $('listo-nombre').textContent = d.nombre;
    irAPaso(3);

    const enPywebview = typeof window.pywebview !== 'undefined';
    const btnGuardar  = $('btn-guardar-pdf');
    const btnDescargar = $('btn-descargar-pdf');
    const btnAbrir    = $('btn-abrir-pdf');

    if (enPywebview) {
        btnGuardar.style.display  = '';
        btnDescargar.style.display = 'none';
        btnAbrir.style.display    = '';
    } else {
        btnGuardar.style.display  = 'none';
        btnDescargar.style.display = '';
        btnDescargar.href     = d.descarga;
        btnDescargar.download = d.nombre;
        btnAbrir.style.display = 'none';
    }
}

$('btn-guardar-pdf').addEventListener('click', () => {
    if (typeof window.pywebview !== 'undefined') {
        window.pywebview.api.guardar_pdf(estado.idTrabajo)
            .catch(err => console.error('guardar_pdf error:', err));
    }
});

$('btn-abrir-pdf').addEventListener('click', () => {
    if (typeof window.pywebview !== 'undefined' && estado.descargaUrl) {
        // Pasar la URL local; el backend sabe la ruta real
        window.pywebview.api.abrir_pdf(estado.idTrabajo)
            .catch(err => console.error('abrir_pdf error:', err));
    }
});

$('btn-nueva-partitura').addEventListener('click', () => {
    reiniciar();
});

function reiniciar() {
    estado.idTrabajo    = null;
    estado.resultado    = null;
    estado.correciones  = {};
    estado.dudosaIds    = [];
    estado.notaActualIdx = 0;
    estado.descargaUrl  = null;
    estado.descargaNombre = null;
    scrollPags.innerHTML = '';
    cerrarSelector();
    mostrarEstadoCarga('carga');
    irAPaso(1);
}

// ============================================================
// Cierre del documento: liberar recursos
// ============================================================
window.addEventListener('beforeunload', () => {
    if (estado.intervaloPoll) clearInterval(estado.intervaloPoll);
});
