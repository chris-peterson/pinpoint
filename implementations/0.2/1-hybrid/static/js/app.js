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

const ROOT_FIELDS = {
  memory: [['event', 'Event'], ['person', 'Person'], ['name', 'Name']],
  music: [['artist', 'Artist'], ['album', 'Album'], ['year', 'Year'], ['track', 'Track'], ['name', 'Name']],
  movie: [['series', 'Series'], ['name', 'Title'], ['year', 'Year']],
  tv: [['show', 'Show'], ['season', 'Season'], ['episode', 'Episode'], ['name', 'Name']],
  podcast: [['show', 'Show'], ['episode', 'Episode'], ['name', 'Name']],
  book: [['author', 'Author'], ['series', 'Series'], ['name', 'Title']],
  comedy: [['artist', 'Artist'], ['name', 'Title'], ['year', 'Year']],
};

const MULTI_VALUE_FIELDS = new Set(['person']);

const ICONS = {
  image: '\u{1F5BC}',
  video: '\u{1F3AC}',
  audio: '\u{1F3B5}',
  document: '\u{1F4C4}',
};

function iconFor(fileClass) {
  return ICONS[fileClass] || ICONS.document;
}

function confidenceBadge(confidence) {
  if (confidence == null) return '';
  const pct = Math.round(confidence * 100);
  let cls = 'conf-low';
  if (confidence >= 0.7) cls = 'conf-high';
  else if (confidence >= 0.4) cls = 'conf-med';
  return `<span class="conf-badge ${cls}">${pct}%</span>`;
}

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// --- Router ---

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
      route === 'home' && (path === '/' || path.startsWith('/browse')) ||
      route === 'review' && path === '/review' ||
      route === 'whats-new' && path === '/whats-new' ||
      route === 'missing' && path === '/missing'
    );
  });

  if (path === '/') await renderHome(content, params);
  else if (path === '/review') await renderReview(content, params);
  else if (path === '/whats-new') await renderWhatsNew(content, params);
  else if (path === '/missing') await renderMissing(content, params);
  else if (path.startsWith('/browse')) await renderBrowse(content, params);
  else if (path.startsWith('/files/')) await renderFileDetail(content, path.split('/')[2]);
  else content.innerHTML = '<div class="empty-state"><h3>Not found</h3></div>';

  await updateSidebar();
}

async function updateSidebar() {
  try {
    const stats = await API.get('/api/stats');

    const reviewBadge = $('#review-badge');
    if (stats.needsReviewCount > 0) {
      reviewBadge.textContent = stats.needsReviewCount;
      reviewBadge.style.display = '';
    } else {
      reviewBadge.style.display = 'none';
    }

    const missingLink = $('#missing-link');
    const missingBadge = $('#missing-badge');
    if (stats.missingCount > 0) {
      missingLink.style.display = '';
      missingBadge.textContent = stats.missingCount;
    } else {
      missingLink.style.display = 'none';
    }

    const sidebar = $('#sidebar-stats');
    let html = `<div class="stat-row"><span>Imported</span><span>${stats.importedCount}</span></div>`;
    if (stats.analyzingCount > 0) {
      html += `<div class="stat-row"><span>Analyzing</span><span class="analyzing-pulse">${stats.analyzingCount}</span></div>`;
    }
    if (stats.needsReviewCount > 0) {
      html += `<div class="stat-row"><span>Needs review</span><span>${stats.needsReviewCount}</span></div>`;
    }
    sidebar.innerHTML = html;
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
        <div class="subtitle">${stats.importedCount} imported${stats.analyzingCount ? `, ${stats.analyzingCount} analyzing` : ''}</div>
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

  if (stats.onThisDay && stats.onThisDay.length > 0) {
    const otdHtml = `
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
    el.insertAdjacentHTML('beforeend', otdHtml);
  }
}

async function loadBrowseHome(el, filterRoot, filterClass) {
  const data = await API.get('/api/browse?path=');

  if (data.subfolders.length === 0 && data.files.length === 0) {
    el.innerHTML = `
      <div class="empty-state">
        <div class="icon">\u{1F4C2}</div>
        <h3>No imported files yet</h3>
        <p>Point Pinpoint at a folder and files will be automatically imported.</p>
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
    const name = (r.output_path || r.source_path || '').split('/').pop();
    html += `
      <li>
        <a class="result-row" href="#/files/${r.id}">
          <span class="r-icon">${iconFor(r.file_class)}</span>
          <span class="r-name">${escapeHtml(name)}</span>
          ${r.favorite ? '<span class="r-star">\u2605</span>' : ''}
          ${confidenceBadge(r.confidence)}
          <span class="r-path">${escapeHtml(r.output_path || r.source_path || '')}</span>
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
          ${confidenceBadge(f.confidence)}
        </a>
      </li>
    `;
  }
  html += '</ul>';
  return html;
}

// --- Review (needs attention) ---

async function renderReview(el, params) {
  const data = await API.get(
    `/api/review?root=${params.get('root') || ''}&file_class=${params.get('file_class') || ''}&max_confidence=${params.get('max_confidence') || ''}`
  );

  let html = `
    <div class="page-header">
      <div>
        <h2>Review</h2>
        <div class="subtitle">
          ${data.needsReview} file${data.needsReview !== 1 ? 's' : ''} need attention
          ${data.totalAnalyzing > 0 ? `&middot; ${data.totalAnalyzing} still analyzing` : ''}
        </div>
      </div>
      <div class="filter-bar">
        <select onchange="location.hash='/review?root='+this.value+'&file_class=${data.filterClass}'">
          <option value="">All roots</option>
          ${data.rootCounts.map(r =>
            `<option value="${r.root}" ${data.filterRoot === r.root ? 'selected' : ''}>${r.root} (${r.cnt})</option>`
          ).join('')}
        </select>
        <select onchange="location.hash='/review?root=${data.filterRoot}&file_class='+this.value">
          <option value="">All types</option>
          ${data.classCounts.map(c =>
            `<option value="${c.file_class}" ${data.filterClass === c.file_class ? 'selected' : ''}>${c.file_class} (${c.cnt})</option>`
          ).join('')}
        </select>
      </div>
    </div>
  `;

  if (data.files.length === 0) {
    html += `
      <div class="empty-state">
        <div class="icon">\u2713</div>
        <h3>All clear</h3>
        <p>No files need review right now.</p>
      </div>
    `;
    el.innerHTML = html;
    return;
  }

  html += '<ul class="results-list">';
  for (const f of data.files) {
    const name = (f.output_path || f.source_path || '').split('/').pop();
    html += `
      <li>
        <a class="result-row" href="#/files/${f.id}">
          <span class="r-icon">${iconFor(f.file_class)}</span>
          <span class="r-name">${escapeHtml(name)}</span>
          ${f.favorite ? '<span class="r-star">\u2605</span>' : ''}
          ${confidenceBadge(f.confidence)}
          <span class="r-tags">${escapeHtml(f.tag_list || '')}</span>
          <span class="r-path">${escapeHtml(f.output_path || '')}</span>
        </a>
      </li>
    `;
  }
  html += '</ul>';

  el.innerHTML = html;
}

// --- What's New ---

async function renderWhatsNew(el) {
  const data = await API.get('/api/whats-new');

  let html = `
    <div class="page-header">
      <div>
        <h2>What's New</h2>
        <div class="subtitle">Recently imported files</div>
      </div>
    </div>
  `;

  if (data.files.length === 0) {
    html += `
      <div class="empty-state">
        <div class="icon">\u{1F4E5}</div>
        <h3>Nothing new</h3>
        <p>No files have been imported yet.</p>
      </div>
    `;
    el.innerHTML = html;
    return;
  }

  html += '<ul class="results-list">';
  for (const f of data.files) {
    const name = (f.output_path || f.source_path || '').split('/').pop();
    html += `
      <li>
        <a class="result-row" href="#/files/${f.id}">
          <span class="r-icon">${iconFor(f.file_class)}</span>
          <span class="r-name">${escapeHtml(name)}</span>
          ${f.favorite ? '<span class="r-star">\u2605</span>' : ''}
          ${confidenceBadge(f.confidence)}
          <span class="r-tags">${escapeHtml(f.tag_list || '')}</span>
          <span class="r-time">${f.imported_at || ''}</span>
        </a>
      </li>
    `;
  }
  html += '</ul>';

  el.innerHTML = html;
}

// --- Missing ---

async function renderMissing(el) {
  const data = await API.get('/api/missing');

  let html = `
    <div class="page-header">
      <div>
        <h2>Missing Files</h2>
        <div class="subtitle">${data.files.length} file${data.files.length !== 1 ? 's' : ''} missing from output</div>
      </div>
      ${data.files.length > 0 ? `
        <button class="btn btn-secondary" id="dismiss-all-btn">Dismiss All</button>
      ` : ''}
    </div>
  `;

  if (data.files.length === 0) {
    html += `
      <div class="empty-state">
        <div class="icon">\u2713</div>
        <h3>No missing files</h3>
      </div>
    `;
    el.innerHTML = html;
    return;
  }

  html += '<ul class="results-list">';
  for (const f of data.files) {
    const name = (f.output_path || f.source_path || '').split('/').pop();
    html += `
      <li class="missing-row" data-id="${f.id}">
        <div class="result-row">
          <span class="r-icon">${iconFor(f.file_class)}</span>
          <span class="r-name">${escapeHtml(name)}</span>
          <span class="r-path">${escapeHtml(f.output_path || '')}</span>
          <button class="btn-dismiss" data-id="${f.id}">Dismiss</button>
        </div>
      </li>
    `;
  }
  html += '</ul>';

  el.innerHTML = html;

  $$('.btn-dismiss', el).forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const id = btn.dataset.id;
      await API.post(`/api/missing/${id}/dismiss`);
      btn.closest('li').remove();
      await updateSidebar();
    });
  });

  const dismissAllBtn = $('#dismiss-all-btn');
  if (dismissAllBtn) {
    dismissAllBtn.addEventListener('click', async () => {
      await API.post('/api/missing/dismiss-all');
      navigate();
    });
  }
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
  const rootFields = ROOT_FIELDS[file.root] || [];

  const fileName = (file.output_path || file.source_path || '').split('/').pop();

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
    <div class="detail-header">
      <h3>${escapeHtml(fileName)}</h3>
      <button class="favorite-btn ${file.favorite ? 'active' : ''}" id="fav-btn">${file.favorite ? '\u2605' : '\u2606'}</button>
    </div>
  `;

  html += `
    <dl class="file-meta">
      <dt>Status</dt><dd>${file.status} ${confidenceBadge(file.confidence)}</dd>
      <dt>Root</dt><dd>${file.root}</dd>
      <dt>Type</dt><dd>${file.file_class}</dd>
      ${file.output_path ? `<dt>Path</dt><dd>${escapeHtml(file.output_path)}</dd>` : ''}
      ${file.source_path ? `<dt>Source</dt><dd>${escapeHtml(file.source_path)}</dd>` : ''}
      ${file.creation_date ? `<dt>Created</dt><dd>${file.creation_date}</dd>` : ''}
      ${file.imported_at ? `<dt>Imported</dt><dd>${file.imported_at}</dd>` : ''}
    </dl>
  `;

  // Tag editing form
  const tagMap = {};
  const tagSourceMap = {};
  for (const t of tags) {
    const [type, ...rest] = t.name.split(':');
    const val = rest.join(':');
    if (MULTI_VALUE_FIELDS.has(type)) {
      tagMap[type] = tagMap[type] || [];
      tagMap[type].push(val);
    } else {
      tagMap[type] = val;
    }
    tagSourceMap[type] = t.source;
  }

  html += `<div class="edit-section">`;
  html += `<h4 class="section-label">Tags</h4>`;
  html += `<form id="tag-form">`;

  for (const [fid, flabel] of rootFields) {
    const source = tagSourceMap[fid] || '';
    const isMulti = MULTI_VALUE_FIELDS.has(fid);
    const val = isMulti ? (tagMap[fid] || []) : (tagMap[fid] || '');

    html += `<div class="field-group">`;
    html += `<label>${escapeHtml(flabel)}`;
    if (source) html += ` <span class="source-badge ${source}">${source}</span>`;
    html += `</label>`;

    if (isMulti) {
      html += `<div class="chip-input" id="chip-${fid}">`;
      for (const v of val) {
        html += `<span class="chip" data-value="${escapeHtml(v)}">${escapeHtml(v)}<span class="remove">\u00d7</span></span>`;
      }
      html += `<input type="text" placeholder="Add ${flabel.toLowerCase()}..." data-field="${fid}">`;
      html += `</div>`;
    } else {
      html += `<input type="text" class="tag-field" name="${fid}" value="${escapeHtml(val)}" placeholder="${flabel}..." data-field="${fid}">`;
    }
    html += `</div>`;
  }

  html += `<div class="path-preview" id="path-preview">${escapeHtml(file.output_path || '')}</div>`;
  html += `<button type="submit" class="btn btn-primary">Save Tags</button>`;
  html += `</form>`;
  html += `</div>`;

  if (actions.length > 0) {
    html += `<div class="action-log"><h4>History</h4>`;
    for (const a of actions) {
      html += `
        <div class="action-entry">
          <span class="verb">${a.verb}</span>
          <span>${a.detail ? escapeHtml(JSON.stringify(JSON.parse(a.detail)).slice(0, 80)) : ''}</span>
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
          const result = await API.post(`/api/files/${file.id}/preview-path`, formData);
          $('#path-preview').textContent = result.path;
        } catch {}
      }, 200);
    });
  });

  // Save tags
  $('#tag-form').addEventListener('submit', async (e) => {
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

    const result = await API.post(`/api/files/${file.id}/tags`, formData);
    if (result.ok) {
      navigate();
    }
  });

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

  // Remove chip
  $$('.chip .remove', el).forEach(btn => {
    btn.addEventListener('click', () => btn.parentElement.remove());
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
