// OmniSearch — Universal File & Everything Discovery Client

let currentResults = [];
let currentQuery = '';
let currentMetrics = null;

document.addEventListener('DOMContentLoaded', () => {
  initSources();
  setupEventListeners();
});

async function initSources() {
  const container = document.getElementById('source-checkboxes');
  try {
    const res = await fetch('/api/sources');
    if (res.ok) {
      const sources = await res.json();
      container.innerHTML = sources.map(s => `
        <label class="checkbox-chip">
          <input type="checkbox" name="source" value="${s.id}" checked>
          <span>${escapeHtml(s.name)}</span>
        </label>
      `).join('');
    }
  } catch (err) {
    console.error('Failed to load sources:', err);
  }
}

function setupEventListeners() {
  const form = document.getElementById('search-form');
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    performSearch();
  });

  const filterSelect = document.getElementById('item-type-filter');
  if (filterSelect) {
    filterSelect.addEventListener('change', () => {
      if (currentResults.length > 0) {
        applyClientFiltersAndRender();
      }
    });
  }

  // Keyboard shortcut: '/' focuses search input
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault();
      document.getElementById('search-query').focus();
    } else if (e.key === 'Escape') {
      closeModal();
    }
  });

  // Export buttons
  document.getElementById('btn-export-json').addEventListener('click', exportJSON);
  document.getElementById('btn-export-csv').addEventListener('click', exportCSV);
}

async function performSearch() {
  const queryInput = document.getElementById('search-query');
  const query = queryInput.value.trim();
  if (!query) return;

  currentQuery = query;
  const matchMode = document.getElementById('match-mode').value;
  const maxResults = parseInt(document.getElementById('max-results').value, 10) || 100;
  const categoryFilter = document.getElementById('item-type-filter').value;
  
  // Selected sources
  const sourceBoxes = document.querySelectorAll('input[name="source"]:checked');
  const sources = Array.from(sourceBoxes).map(b => b.value);

  showLoadingState();

  try {
    const payload = {
      query: query,
      match_mode: matchMode,
      title_only: matchMode === 'TITLE_ONLY',
      sources: sources.length > 0 ? sources : null,
      item_types: (categoryFilter && categoryFilter !== 'DIRECT_ONLY') ? [categoryFilter] : null,
      max_results: maxResults,
      allow_cache: true
    };

    const res = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Search request failed');
    }

    const data = await res.json();
    currentResults = data.results || [];
    currentMetrics = data.metrics;
    applyClientFiltersAndRender(data);
  } catch (err) {
    showErrorState(err.message);
  }
}

function applyClientFiltersAndRender(data) {
  const categoryFilter = document.getElementById('item-type-filter').value;
  let filtered = currentResults;

  if (categoryFilter === 'DIRECT_ONLY') {
    filtered = currentResults.filter(r => Boolean(r.download_url));
  } else if (categoryFilter) {
    filtered = currentResults.filter(r => r.item_type === categoryFilter);
  }

  const renderData = {
    query: currentQuery,
    match_mode: document.getElementById('match-mode').value,
    total_matches: filtered.length,
    results: filtered,
    metrics: currentMetrics || {}
  };
  renderResults(renderData);
}

function showLoadingState() {
  const container = document.getElementById('results-container');
  const metricsBar = document.getElementById('metrics-bar');
  metricsBar.style.display = 'none';

  container.innerHTML = `
    <div class="state-container">
      <div class="spinner"></div>
      <h3>Searching...</h3>
      <p style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--text-muted);">Discovering files, websites, and direct downloads.</p>
    </div>
  `;
}

function showErrorState(message) {
  const container = document.getElementById('results-container');
  const metricsBar = document.getElementById('metrics-bar');
  metricsBar.style.display = 'none';

  container.innerHTML = `
    <div class="state-container" style="border-color: var(--accent-rose);">
      <h3 style="color: var(--accent-rose);">Search Encountered an Error</h3>
      <p style="margin-top: 0.5rem;">${escapeHtml(message)}</p>
    </div>
  `;
}

function renderResults(data) {
  const container = document.getElementById('results-container');
  const metricsBar = document.getElementById('metrics-bar');
  const results = data.results || [];
  const metrics = data.metrics || {};

  // Render metrics bar
  metricsBar.style.display = 'flex';
  metricsBar.innerHTML = `
    <div class="metrics-items">
      <div>Found: <span class="metric-highlight">${results.length} results</span></div>
      <div>Retrieved: <span class="metric-highlight">${metrics.candidates_retrieved || 0} candidates</span></div>
      <div>Deduplicated: <span class="metric-highlight">${metrics.duplicates_filtered || 0}</span></div>
      <div>Time: <span class="metric-highlight">${metrics.duration_ms || 0} ms</span></div>
      <div>Sources: <span class="metric-highlight">${(metrics.sources_contacted || []).length} active</span></div>
    </div>
    <div>
      <span style="font-size: 0.8rem; color: var(--text-muted);">Mode: ${escapeHtml(data.match_mode || '')}</span>
    </div>
  `;

  if (results.length === 0) {
    container.innerHTML = `
      <div class="state-container">
        <h3>No Matching Files or Pages Found</h3>
        <p style="margin-top: 0.5rem;">No files or downloads satisfied the strict keyword constraints for <strong>${escapeHtml(data.query)}</strong>.</p>
      </div>
    `;
    return;
  }

  // Render list items
  const listHtml = `
    <div class="results-list">
      ${results.map((item, index) => renderListItem(item, index)).join('')}
    </div>
  `;
  container.innerHTML = listHtml;
}

function getItemTypeDetails(itemType) {
  switch (itemType) {
    case 'WEB_PAGE':
      return { icon: '🌐', label: 'Website', cssClass: 'item-type-web' };
    case 'ARCHIVE':
      return { icon: '📦', label: 'Archive', cssClass: 'item-type-archive' };
    case 'DOCUMENT':
      return { icon: '📄', label: 'Document', cssClass: 'item-type-doc' };
    case 'SOFTWARE':
      return { icon: '💾', label: 'Software', cssClass: 'item-type-software' };
    case 'VIDEO':
      return { icon: '🎬', label: 'Video', cssClass: 'item-type-video' };
    case 'AUDIO':
      return { icon: '🎵', label: 'Audio', cssClass: 'item-type-audio' };
    case 'DATASET':
      return { icon: '📊', label: 'Dataset', cssClass: 'item-type-file' };
    default:
      return { icon: '📁', label: 'File', cssClass: 'item-type-file' };
  }
}

function getHostname(urlStr) {
  try {
    return new URL(urlStr).hostname;
  } catch (e) {
    return '';
  }
}

function renderListItem(item, index) {
  const prov = item.provenance || {};
  const matchedTerms = prov.matched_terms || [];
  const matchType = prov.match_type || 'WORD_BOUNDARY';
  const typeDetails = getItemTypeDetails(item.item_type);

  // Highlight title and description
  const highlightedTitle = highlightMatches(item.title || item.file_name || 'Untitled Discovery', matchedTerms);
  const highlightedDesc = highlightMatches(item.description || 'No description available.', matchedTerms);

  const isWebPage = item.item_type === 'WEB_PAGE';
  const mainActionLabel = isWebPage ? '↗ Visit' : '↗ Page';
  const mainActionClass = isWebPage ? 'btn-visit-web' : 'btn-visit-page';
  const hostname = getHostname(item.canonical_url);

  return `
    <article class="result-list-item">
      <div class="list-item-avatar ${typeDetails.cssClass}" title="${typeDetails.label}">
        ${typeDetails.icon}
      </div>

      <div class="list-item-main">
        <div class="list-item-row-top">
          <div class="list-item-title-group">
            <h2 class="list-item-title">
              <a href="${escapeHtml(item.download_url || item.canonical_url)}" target="_blank" rel="noopener noreferrer">
                ${highlightedTitle}
              </a>
            </h2>
            <div class="list-item-meta-pills">
              <span class="item-type-badge ${typeDetails.cssClass}">${typeDetails.label}</span>
              ${item.file_extension ? `<span class="ext-badge">.${escapeHtml(item.file_extension)}</span>` : ''}
              ${item.file_size_human ? `<span class="file-size-badge">💾 ${escapeHtml(item.file_size_human)}</span>` : ''}
              <span class="platform-badge-inline">${escapeHtml(item.platform || 'Web')}</span>
              ${item.relevance_score ? `<span class="score-badge-inline">${item.relevance_score.toFixed(1)}</span>` : ''}
            </div>
          </div>

          <div class="list-item-actions">
            ${item.download_url ? `<a class="list-action-btn btn-direct-dl" href="${escapeHtml(item.download_url)}" target="_blank" rel="noopener noreferrer" title="1-Click Direct Download">⬇ Download</a>` : ''}
            <a class="list-action-btn ${mainActionClass}" href="${escapeHtml(item.canonical_url)}" target="_blank" rel="noopener noreferrer">${mainActionLabel}</a>
            <button class="list-action-btn btn-audit" onclick="openProvenanceModal(${index})" title="Inspect match provenance">🔍 Info</button>
          </div>
        </div>

        <div class="list-item-row-bottom">
          <span class="list-item-url" title="${escapeHtml(item.canonical_url)}">${escapeHtml(hostname || item.canonical_url)}</span>
          <span class="dot-sep">•</span>
          <span class="list-item-snippet">${highlightedDesc}</span>
          <div class="list-item-prov-inline">
            <span class="prov-pill ${getMatchPillClass(matchType)}">${matchType.replace(/_/g, ' ')}</span>
            ${(prov.matched_fields || []).slice(0, 2).map(f => `<span class="prov-pill meta-match">${escapeHtml(f)}</span>`).join('')}
          </div>
        </div>
      </div>
    </article>
  `;
}

function getMatchPillClass(matchType) {
  if (matchType === 'EXACT_PHRASE') return 'exact-phrase';
  if (matchType === 'TITLE_AND_METADATA' || matchType === 'WORD_BOUNDARY') return 'title-match';
  return 'meta-match';
}

function highlightMatches(text, terms) {
  if (!text || !terms || terms.length === 0) return escapeHtml(text);
  let safeText = escapeHtml(text);

  terms.forEach(term => {
    if (!term.trim()) return;
    const escapedTerm = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(?<!\\w)(${escapedTerm})(?!\\w)`, 'gi');
    safeText = safeText.replace(regex, '<mark class="match-hl">$1</mark>');
  });

  return safeText;
}

function openProvenanceModal(index) {
  const item = currentResults[index];
  if (!item) return;

  const prov = item.provenance || {};
  let modal = document.getElementById('provenance-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'provenance-modal';
    modal.className = 'modal-backdrop';
    document.body.appendChild(modal);
  }

  modal.innerHTML = `
    <div class="modal-dialog">
      <div class="modal-header">
        <h3>Match Provenance & Audit</h3>
        <button class="modal-close" onclick="closeModal()">×</button>
      </div>
      <div class="modal-body">
        <p><strong>Item Title:</strong> ${escapeHtml(item.title || item.file_name || '')}</p>
        <p><strong>Platform:</strong> ${escapeHtml(item.platform || '')}</p>
        <p><strong>Category:</strong> ${escapeHtml(item.item_type || '')}</p>
        <p><strong>Canonical Page:</strong> <a href="${escapeHtml(item.canonical_url)}" target="_blank" style="color: var(--accent-cyan); word-break: break-all;">${escapeHtml(item.canonical_url)}</a></p>
        ${item.download_url ? `<p><strong>Direct Download:</strong> <a href="${escapeHtml(item.download_url)}" target="_blank" style="color: var(--accent-emerald); word-break: break-all;">${escapeHtml(item.download_url)}</a></p>` : ''}
        <p><strong>Match Type:</strong> ${escapeHtml(prov.match_type || '')}</p>
        <p><strong>Matched Terms:</strong> ${(prov.matched_terms || []).map(t => `<span class="syntax-pill">${escapeHtml(t)}</span>`).join(' ')}</p>
        <p><strong>Matched Fields:</strong> ${(prov.matched_fields || []).map(f => `<span class="syntax-pill">${escapeHtml(f)}</span>`).join(' ')}</p>
        <p><strong>Relevance Score:</strong> ${item.relevance_score ? item.relevance_score.toFixed(2) : 'N/A'}</p>
        
        <h4 style="margin-top: 1rem; margin-bottom: 0.5rem;">Raw Metadata:</h4>
        <pre class="provenance-raw-json">${escapeHtml(JSON.stringify(item.raw_metadata || {}, null, 2))}</pre>
      </div>
    </div>
  `;

  modal.style.display = 'flex';
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });
}

function closeModal() {
  const modal = document.getElementById('provenance-modal');
  if (modal) modal.style.display = 'none';
}

function exportJSON() {
  if (currentResults.length === 0) {
    alert('No results to export.');
    return;
  }
  const blob = new Blob([JSON.stringify(currentResults, null, 2)], { type: 'application/json' });
  downloadBlob(blob, `omnisearch-${sanitizeFilename(currentQuery)}.json`);
}

function exportCSV() {
  if (currentResults.length === 0) {
    alert('No results to export.');
    return;
  }
  const headers = ['Rank', 'Title', 'Platform', 'Type', 'Extension', 'Size', 'Download URL', 'Canonical URL', 'Score'];
  const rows = currentResults.map((item, idx) => [
    idx + 1,
    `"${(item.title || item.file_name || '').replace(/"/g, '""')}"`,
    `"${(item.platform || '').replace(/"/g, '""')}"`,
    `"${(item.item_type || '').replace(/"/g, '""')}"`,
    `"${(item.file_extension || '').replace(/"/g, '""')}"`,
    `"${(item.file_size_human || '').replace(/"/g, '""')}"`,
    `"${(item.download_url || '').replace(/"/g, '""')}"`,
    `"${(item.canonical_url || '').replace(/"/g, '""')}"`,
    item.relevance_score || 0
  ]);

  const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, `omnisearch-${sanitizeFilename(currentQuery)}.csv`);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function sanitizeFilename(str) {
  return (str || 'results').replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
