const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

const API = {
  async get(url) {
    const resp = await fetch(url);
    return resp.json();
  },
  async post(url, body = {}) {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return resp.json();
  },
};

const ROOTS = ['memory', 'music', 'movie', 'tv', 'podcast', 'book', 'comedy'];

const ICONS = {
  image: '\u{1F5BC}',
  video: '\u{1F3AC}',
  audio: '\u{1F3B5}',
  document: '\u{1F4C4}',
};

function iconFor(fileClass) {
  return ICONS[fileClass] || ICONS.document;
}

// --- Router ---

const routes = {
  '/': renderHome,
  '/queue': renderQueue,
  '/library': renderLibrary,
  '/browse': renderBrowse,
  '/files': renderFileDetail,
};

function getRoute() {
  const hash = location.hash.slice(1) || '/';
  const [path, query] = hash.split('?');
  const params = new URLSearchParams(query || '');
  return { path, params };
}

async function navigate() {
  const { path, params } = getRoute();
  const content = $('#content');

  $$('.nav-link').forEach(link => {
    const route = link.dataset.route;
    link.classList.toggle('active',
      route === 'home' && path === '/' ||
      route === 'queue' && path === '/queue' ||
      route === 'library' && (path === '/library' || path === '/browse')
    );
  });

  if (path === '/') await renderHome(content, params);
  else if (path === '/queue') await renderQueue(content, params);
  else if (path === '/library') await renderLibrary(content, params);
  else if (path.startsWith('/browse')) await renderBrowse(content, params);
  else if (path.startsWith('/files/')) await renderFileDetail(content, path.split('/')[2]);
  else content.innerHTML = '<div class="empty-state"><h3>Not found</h3></div>';

  await updateBadge();
}

async function updateBadge() {
  try {
    const stats = await API.get('/api/stats');
    const badge = $('#queue-badge');
    if (stats.pendingCount > 0) {
      badge.textContent = stats.pendingCount;
      badge.style.display = '';
    } else {
      badge.style.display = 'none';
    }

    const sidebar = $('#sidebar-stats');
    sidebar.innerHTML = `
      <div class="stat-row"><span>Managed</span><span>${stats.managedCount}</span></div>
      <div class="stat-row"><span>Pending</span><span>${stats.pendingCount}</span></div>
      ${stats.missingCount ? `<div class="stat-row"><span>Missing</span><span>${stats.missingCount}</span></div>` : ''}
    `;
  } catch {}
}

window.addEventListener('hashchange', navigate);
window.addEventListener('load', navigate);

// --- Home ---

async function renderHome(el, params) {
  const stats = await API.get('/api/stats');
  const q = params.get('q') || '';
  const filterRoot = params.get('root') || '';
  const filterClass = params.get('file_class') || '';

  let html = `
    <div class="page-header">
      <div>
        <h2>Home</h2>
        <div class="subtitle">${stats.managedCount} managed, ${stats.pendingCount} pending</div>
      </div>
      <div class="filter-bar">
        <select onchange="location.hash='/?root='+this.value+'&file_class=${filterClass}'">
          <option value="">All roots</option>
          ${stats.rootCounts.map(r =>
            `<option value="${r.root}" ${filterRoot === r.root ? 'selected' : ''}>${r.root} (${r.cnt})</option>`
          ).join('')}
        </select>
        <select onchange="location.hash='/?root=${filterRoot}&file_class='+this.value">
          <option value="">All types</option>
          ${stats.classCounts.map(c =>
            `<option value="${c.file_class}" ${filterClass === c.file_class ? 'selected' : ''}>${c.file_class} (${c.cnt})</option>`
          ).join('')}
        </select>
      </div>
    </div>

    <div class="search-bar">
      <input type="text" id="search-input" placeholder="Search files, tags, metadata..." value="${escapeHtml(q)}">
    </div>

    <div id="search-results"></div>
    <div id="browse-content"></div>
  `;

  el.innerHTML = html;

  const searchInput = $('#search-input');
  const searchResults = $('#search-results');
  const browseContent = $('#browse-content');

  let debounce;
  searchInput.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(async () => {
      const val = searchInput.value.trim();
      if (val.length >= 2) {
        const data = await API.get(`/api/search?q=${encodeURIComponent(val)}`);
        searchResults.innerHTML = renderResultsList(data.results);
        browseContent.innerHTML = '';
      } else {
        searchResults.innerHTML = '';
        await loadBrowseHome(browseContent, filterRoot, filterClass);
      }
    }, 300);
  });

  if (q) {
    const data = await API.get(`/api/search?q=${encodeURIComponent(q)}`);
    searchResults.innerHTML = renderResultsList(data.results);
  } else {
    await loadBrowseHome(browseContent, filterRoot, filterClass);
  }

  if (stats.onThisDay.length > 0) {
    el.innerHTML += `
      <div class="on-this-day">
        <h3>On This Day</h3>
        <div class="otd-strip">
          ${stats.onThisDay.map(item => `
            <a class="otd-card" href="#/files/${item.id}">
              <div class="thumb">
                ${item.fileClass === 'image'
                  ? `<img src="/preview/${item.id}" alt="" loading="lazy">`
                  : `<span style="font-size:2rem;opacity:0.3">${iconFor(item.fileClass)}</span>`
                }
              </div>
              <div class="year-label">${item.year}</div>
            </a>
          `).join('')}
        </div>
      </div>
    `;
  }
}

async function loadBrowseHome(el, filterRoot, filterClass) {
  let url = '/api/browse?path=';
  if (filterRoot) url += `&root=${filterRoot}`;
  if (filterClass) url += `&file_class=${filterClass}`;
  const data = await API.get(url);

  if (data.subfolders.length === 0 && data.files.length === 0) {
    el.innerHTML = `
      <div class="empty-state">
        <div class="icon">\u{1F4C2}</div>
        <h3>No managed files yet</h3>
        <p>Accept files from the queue to populate your library.</p>
      </div>
    `;
    return;
  }

  let html = '';
  if (data.subfolders.length > 0) {
    html += '<div class="folder-grid">';
    for (const sub of data.subfolders) {
      html += `
        <a class="folder-card" href="#/browse?path=${encodeURIComponent(sub.key)}">
          <div class="hero">
            ${sub.heroId
              ? `<img src="/preview/${sub.heroId}" alt="" loading="lazy">`
              : '<span class="icon-placeholder">\u{1F4C1}</span>'
            }
          </div>
          <div class="info">
            <div class="name">${escapeHtml(sub.name)}</div>
            <div class="meta">${sub.count} file${sub.count !== 1 ? 's' : ''}</div>
          </div>
        </a>
      `;
    }
    html += '</div>';
  }

  if (data.files.length > 0) {
    html += renderFileList(data.files);
  }

  el.innerHTML = html;
}

function renderResultsList(results) {
  if (!results.length) return '';
  let html = '<ul class="results-list">';
  for (const r of results) {
    const name = (r.managed_path || r.source_path || '').split('/').pop();
    html += `
      <li>
        <a class="result-row" href="#/files/${r.id}">
          <span class="r-icon">${iconFor(r.file_class)}</span>
          <span class="r-name">${escapeHtml(name)}</span>
          ${r.favorite ? '<span class="r-star">\u2605</span>' : ''}
          <span class="r-path">${escapeHtml(r.managed_path || r.source_path || '')}</span>
        </a>
      </li>
    `;
  }
  html += '</ul>';
  return html;
}

function renderFileList(files) {
  let html = '<ul class="results-list">';
  for (const f of files) {
    html += `
      <li>
        <a class="result-row" href="#/files/${f.id}">
          <span class="r-icon">${iconFor(f.fileClass)}</span>
          <span class="r-name">${escapeHtml(f.name)}</span>
          ${f.favorite ? '<span class="r-star">\u2605</span>' : ''}
        </a>
      </li>
    `;
  }
  html += '</ul>';
  return html;
}

// --- Queue ---

async function renderQueue(el, params) {
  const data = await API.get(
    `/api/queue?root=${params.get('root') || ''}&file_class=${params.get('file_class') || ''}`
  );

  let html = `
    <div class="page-header">
      <div>
        <h2>Queue</h2>
        <div class="subtitle">${data.totalPending} file${data.totalPending !== 1 ? 's' : ''} pending</div>
      </div>
      <div class="filter-bar">
        <select onchange="location.hash='/queue?root='+this.value+'&file_class=${data.filterClass}'">
          <option value="">All roots</option>
          ${data.rootCounts.map(r =>
            `<option value="${r.root}" ${data.filterRoot === r.root ? 'selected' : ''}>${r.root} (${r.cnt})</option>`
          ).join('')}
        </select>
        <select onchange="location.hash='/queue?root=${data.filterRoot}&file_class='+this.value">
          <option value="">All types</option>
          ${data.classCounts.map(c =>
            `<option value="${c.file_class}" ${data.filterClass === c.file_class ? 'selected' : ''}>${c.file_class} (${c.cnt})</option>`
          ).join('')}
        </select>
      </div>
    </div>
  `;

  if (!data.file) {
    html += `
      <div class="empty-state">
        <div class="icon">\u2713</div>
        <h3>Queue is empty</h3>
        <p>All files have been reviewed. New files will appear here when discovered.</p>
      </div>
    `;
    el.innerHTML = html;
    return;
  }

  const file = data.file;
  const rootFields = data.rootFields || [];
  const expectedTags = data.expectedTags || [];
  const fieldDefaults = data.fieldDefaults || {};
  const filenameDefs = data.filenameDefs || {};
  const metadataDefs = data.metadataDefs || {};
  const multiValueFields = data.multiValueFields || [];
  const pathPreview = data.pathPreview || '';
  const folderCount = data.folderCount || 0;
  const folderReady = data.folderReady || false;
  const sourceFolder = data.sourceFolder || '';

  const fileName = file.source_path.split('/').pop();

  html += `<div class="queue-layout">`;

  // Preview
  html += `<div>`;
  html += `<div class="preview-panel">`;
  if (file.file_class === 'image') {
    html += `<img src="/preview/${file.id}" alt="Preview">`;
  } else if (file.file_class === 'video') {
    html += `<video src="/preview/${file.id}" controls style="max-width:100%"></video>`;
  } else if (file.file_class === 'audio') {
    html += `<div class="audio-wrap"><div class="audio-icon">\u266B</div><audio src="/preview/${file.id}" controls style="width:100%"></audio></div>`;
  } else {
    html += `<div class="empty-state"><div class="icon">\u{1F4C4}</div><p>No preview</p></div>`;
  }
  html += `</div>`;

  html += `
    <dl class="file-meta mt-1">
      <dt>File</dt><dd>${escapeHtml(fileName)}</dd>
      <dt>Source</dt><dd>${escapeHtml(file.source_path)}</dd>
      ${file.creation_date ? `<dt>Created</dt><dd>${file.creation_date}</dd>` : ''}
    </dl>
  `;

  if (folderCount > 1) {
    html += `<div class="mt-1" style="font-size:0.8rem;color:var(--text-faint)">\u{1F4C1} ${folderCount} files from this folder</div>`;
  }
  html += `</div>`;

  // Tag panel
  html += `<div class="tag-panel">`;
  html += `<h3>Tags</h3>`;

  html += `<div class="root-selector">`;
  for (const root of ROOTS) {
    html += `<span class="root-pill ${file.root === root ? 'active' : ''}">${root}</span>`;
  }
  html += `</div>`;

  html += `<form id="accept-form">`;
  for (const [fid, flabel] of rootFields) {
    const isExpected = expectedTags.includes(fid);
    const defaultVal = fieldDefaults[fid] || '';
    const isFromMetadata = fid in metadataDefs;
    const isFromFilename = fid in filenameDefs && !isFromMetadata;

    html += `<div class="field-group">`;
    html += `<label>`;
    if (isExpected && !defaultVal) html += `<span class="expected-dot"></span>`;
    html += escapeHtml(flabel);
    if (isFromMetadata) html += ` <span class="source-badge metadata">metadata</span>`;
    else if (isFromFilename) html += ` <span class="source-badge filename">filename</span>`;
    html += `</label>`;

    if (multiValueFields.includes(fid)) {
      html += `<div class="chip-input" id="chip-${fid}"><input type="text" placeholder="Add ${flabel.toLowerCase()}..." data-field="${fid}"></div>`;
    } else {
      const cls = isFromMetadata ? 'from-metadata' : isFromFilename ? 'from-filename' : '';
      html += `<input type="text" class="tag-field ${cls}" name="${fid}" value="${escapeHtml(defaultVal)}" placeholder="${flabel}..." data-field="${fid}">`;
    }
    html += `</div>`;
  }

  html += `<div class="path-preview" id="path-preview">${escapeHtml(pathPreview)}</div>`;

  html += `
    <div class="btn-group">
      <button type="submit" class="btn btn-primary">Accept</button>
      <button type="button" class="btn btn-secondary" id="skip-btn">Skip</button>
      <button type="button" class="btn btn-danger" id="reject-btn">Reject</button>
    </div>
  `;

  if (folderCount > 1) {
    html += `<div class="folder-accept mt-2">`;
    html += `<div style="border-top:1px solid var(--border);padding-top:0.75rem">`;
    if (folderReady) {
      html += `<button type="button" class="btn btn-primary" style="width:100%" id="accept-folder-btn">Accept all ${folderCount} files in folder</button>`;
      html += `<div style="font-size:0.7rem;color:var(--text-faint);margin-top:0.3rem;text-align:center">All files have complete metadata</div>`;
    } else {
      html += `<button type="button" class="btn btn-secondary" style="width:100%;opacity:0.6" id="accept-folder-btn">Accept all ${folderCount} anyway...</button>`;
      html += `<div style="font-size:0.7rem;color:var(--warning);margin-top:0.3rem;text-align:center">Some files missing expected tags</div>`;
    }
    html += `</div></div>`;
  }

  html += `</form>`;
  html += `</div>`; // tag-panel
  html += `</div>`; // queue-layout

  el.innerHTML = html;

  // Wire up events
  const fileId = file.id;

  // Path preview debounce
  let previewDebounce;
  $$('.tag-field', el).forEach(input => {
    input.addEventListener('input', () => {
      clearTimeout(previewDebounce);
      previewDebounce = setTimeout(async () => {
        const formData = {};
        $$('.tag-field', el).forEach(inp => {
          if (inp.value.trim()) formData[inp.dataset.field] = inp.value.trim();
        });
        try {
          const result = await API.post(`/api/files/${fileId}/preview-path`, formData);
          $('#path-preview').textContent = result.path;
        } catch {}
      }, 200);
    });
  });

  // Accept
  $('#accept-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = {};
    $$('.tag-field', el).forEach(input => {
      if (input.value.trim()) formData[input.dataset.field] = input.value.trim();
    });
    $$('.chip-input', el).forEach(container => {
      const field = $('input', container).dataset.field;
      const chips = $$('.chip', container);
      const values = chips.map(c => c.dataset.value);
      if (values.length > 0) formData[field] = values;
    });

    const result = await API.post(`/api/files/${fileId}/accept`, formData);
    if (result.ok) navigate();
    else alert('Error: ' + (result.error || 'Unknown'));
  });

  // Skip
  $('#skip-btn').addEventListener('click', async () => {
    await API.post(`/api/files/${fileId}/skip`);
    navigate();
  });

  // Reject
  $('#reject-btn').addEventListener('click', async () => {
    if (!confirm('Reject this file? It will be removed from the queue.')) return;
    await API.post(`/api/files/${fileId}/reject`);
    navigate();
  });

  // Accept folder
  const folderBtn = $('#accept-folder-btn');
  if (folderBtn) {
    folderBtn.addEventListener('click', async () => {
      if (!confirm(`Accept all files in this folder?\n\n${sourceFolder}`)) return;
      const result = await API.post('/api/folder/accept', { folder: sourceFolder });
      if (result.ok) navigate();
      else alert('Error: ' + (result.error || 'Unknown'));
    });
  }

  // Chip input
  $$('.chip-input', el).forEach(container => {
    const input = $('input', container);
    const field = input.dataset.field;

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        const val = input.value.trim().replace(/,$/,'');
        if (val) addChip(container, field, val);
        input.value = '';
      }
      if (e.key === 'Backspace' && !input.value) {
        const last = container.querySelector('.chip:last-of-type');
        if (last) last.remove();
      }
    });

    container.addEventListener('click', () => input.focus());
  });
}

function addChip(container, field, value) {
  const chip = document.createElement('span');
  chip.className = 'chip';
  chip.dataset.value = value;
  chip.innerHTML = `${escapeHtml(value)}<span class="remove">\u00d7</span>`;
  chip.querySelector('.remove').addEventListener('click', () => chip.remove());
  container.insertBefore(chip, container.querySelector('input'));
}

// --- Library ---

async function renderLibrary(el) {
  const data = await API.get('/api/library');

  let html = `
    <div class="page-header">
      <div>
        <h2>Library</h2>
        <div class="subtitle">${data.files.length} managed files</div>
      </div>
    </div>
  `;

  if (data.files.length === 0) {
    html += `<div class="empty-state"><div class="icon">\u{1F4DA}</div><h3>No files yet</h3><p>Accept files from the queue.</p></div>`;
  } else {
    html += '<ul class="results-list">';
    for (const f of data.files) {
      const name = (f.managed_path || f.source_path || '').split('/').pop();
      html += `
        <li>
          <a class="result-row" href="#/files/${f.id}">
            <span class="r-icon">${iconFor(f.file_class)}</span>
            <span class="r-name">${escapeHtml(name)}</span>
            ${f.favorite ? '<span class="r-star">\u2605</span>' : ''}
            <span class="r-path">${escapeHtml(f.managed_path || '')}</span>
          </a>
        </li>
      `;
    }
    html += '</ul>';
  }

  el.innerHTML = html;
}

// --- Browse ---

async function renderBrowse(el, params) {
  const folderPath = params.get('path') || '';
  const data = await API.get(`/api/browse?path=${encodeURIComponent(folderPath)}`);

  let html = `<div class="breadcrumbs"><a href="#/">Home</a>`;
  for (const crumb of data.breadcrumbs) {
    html += ` <span class="sep">/</span> `;
    if (crumb === data.breadcrumbs[data.breadcrumbs.length - 1]) {
      html += `<span>${escapeHtml(crumb.label)}</span>`;
    } else {
      html += `<a href="#/browse?path=${encodeURIComponent(crumb.path)}">${escapeHtml(crumb.label)}</a>`;
    }
  }
  html += `</div>`;

  html += `
    <div class="page-header">
      <h2>${escapeHtml(data.folderName || 'Browse')}</h2>
      <div class="subtitle">
        ${data.files.length} file${data.files.length !== 1 ? 's' : ''}${
          data.subfolders.length ? `, ${data.subfolders.length} subfolder${data.subfolders.length !== 1 ? 's' : ''}` : ''
        }
      </div>
    </div>
  `;

  if (data.subfolders.length > 0) {
    html += '<div class="folder-grid mb-2">';
    for (const sub of data.subfolders) {
      html += `
        <a class="folder-card" href="#/browse?path=${encodeURIComponent(sub.key)}">
          <div class="hero">
            ${sub.heroId
              ? `<img src="/preview/${sub.heroId}" alt="" loading="lazy">`
              : '<span class="icon-placeholder">\u{1F4C1}</span>'
            }
          </div>
          <div class="info">
            <div class="name">${escapeHtml(sub.name)}</div>
            <div class="meta">${sub.count} file${sub.count !== 1 ? 's' : ''}</div>
          </div>
        </a>
      `;
    }
    html += '</div>';
  }

  if (data.files.length > 0) {
    html += renderFileList(data.files);
  }

  if (data.files.length === 0 && data.subfolders.length === 0) {
    html += `<div class="empty-state"><div class="icon">\u{1F4C2}</div><h3>Empty folder</h3></div>`;
  }

  el.innerHTML = html;
}

// --- File Detail ---

async function renderFileDetail(el, fileId) {
  const data = await API.get(`/api/files/${fileId}`);
  if (data.error) {
    el.innerHTML = `<div class="empty-state"><h3>File not found</h3></div>`;
    return;
  }

  const file = data.file;
  const tags = data.tags || [];
  const actions = data.actions || [];

  const fileName = (file.managed_path || file.source_path || '').split('/').pop();

  let html = `<div class="file-detail-layout">`;

  // Preview
  html += `<div>`;
  html += `<div class="preview-panel">`;
  if (file.file_class === 'image') {
    html += `<img src="/preview/${file.id}" alt="Preview">`;
  } else if (file.file_class === 'video') {
    html += `<video src="/preview/${file.id}" controls style="max-width:100%"></video>`;
  } else if (file.file_class === 'audio') {
    html += `<div class="audio-wrap"><div class="audio-icon">\u266B</div><audio src="/preview/${file.id}" controls style="width:100%"></audio></div>`;
  } else {
    html += `<div class="empty-state"><div class="icon">\u{1F4C4}</div><p>No preview</p></div>`;
  }
  html += `</div></div>`;

  // Sidebar
  html += `<div class="detail-sidebar">`;
  html += `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem">
      <h3 style="margin:0">${escapeHtml(fileName)}</h3>
      <button class="favorite-btn ${file.favorite ? 'active' : ''}" id="fav-btn">${file.favorite ? '\u2605' : '\u2606'}</button>
    </div>
  `;

  html += `
    <dl class="file-meta">
      <dt>Status</dt><dd>${file.status}</dd>
      <dt>Root</dt><dd>${file.root}</dd>
      <dt>Type</dt><dd>${file.file_class}</dd>
      ${file.managed_path ? `<dt>Path</dt><dd>${escapeHtml(file.managed_path)}</dd>` : ''}
      ${file.source_path ? `<dt>Source</dt><dd>${escapeHtml(file.source_path)}</dd>` : ''}
      ${file.creation_date ? `<dt>Created</dt><dd>${file.creation_date}</dd>` : ''}
    </dl>
  `;

  if (tags.length > 0) {
    html += `<div class="mt-2"><h4 style="font-size:0.8rem;font-weight:500;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-faint);margin-bottom:0.4rem">Tags</h4>`;
    html += `<div class="tag-list">`;
    for (const t of tags) {
      html += `<span class="tag-chip">${escapeHtml(t.name)}</span>`;
    }
    html += `</div></div>`;
  }

  if (actions.length > 0) {
    html += `<div class="action-log"><h4>History</h4>`;
    for (const a of actions) {
      html += `
        <div class="action-entry">
          <span class="verb">${a.verb}</span>
          <span>${a.detail ? escapeHtml(JSON.stringify(JSON.parse(a.detail)).slice(0, 60)) : ''}</span>
          <span class="ts">${a.timestamp || ''}</span>
        </div>
      `;
    }
    html += `</div>`;
  }

  html += `</div>`; // detail-sidebar
  html += `</div>`; // file-detail-layout

  el.innerHTML = html;

  // Favorite toggle
  $('#fav-btn').addEventListener('click', async () => {
    const result = await API.post(`/api/files/${file.id}/favorite`);
    if (result.ok) {
      const btn = $('#fav-btn');
      btn.classList.toggle('active', result.favorite);
      btn.textContent = result.favorite ? '\u2605' : '\u2606';
    }
  });
}

// --- Helpers ---

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
