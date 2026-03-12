
/**
 * API Service - handles all backend API calls
 */

// Use environment variable for production, fallback to localhost for development
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

/**
 * Generic fetch wrapper with error handling
 */
async function fetchAPI(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
    const headers = {
        ...options.headers,
    };

    if (!isFormData && options.body !== undefined) {
        headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(url, {
        headers,
        ...options,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

// ================== Novels API ==================

export async function getNovels(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.search) queryParams.set('search', params.search);
    if (params.genre) queryParams.set('genre', params.genre);
    if (params.limit) queryParams.set('limit', params.limit);
    if (params.offset) queryParams.set('offset', params.offset);

    const query = queryParams.toString();
    return fetchAPI(`/novels${query ? `?${query}` : ''}`);
}

export async function getNovel(slug) {
    return fetchAPI(`/novels/${slug}`);
}

export async function syncNovels() {
    return fetchAPI('/novels/sync', { method: 'POST' });
}

export async function updateNovel(slug, tocUrl = null) {
    const body = tocUrl && tocUrl.trim()
        ? JSON.stringify({ toc_url: tocUrl.trim() })
        : undefined;

    return fetchAPI(`/novels/${slug}/update`, {
        method: 'POST',
        body,
    });
}

export async function importNovelFolder(files) {
    const form = new FormData();
    let folderName = '';

    files.forEach((file) => {
        const relativePath = file.webkitRelativePath || file.name;
        if (!folderName && file.webkitRelativePath) {
            folderName = file.webkitRelativePath.split('/')[0] || '';
        }
        form.append('files', file, relativePath);
    });

    if (folderName) {
        form.append('folder_name', folderName);
    }

    return fetchAPI('/novels/import-folder', {
        method: 'POST',
        body: form,
    });
}

// ================== Chapters API ==================

export async function getChapters(slug, params = {}) {
    const queryParams = new URLSearchParams();
    if (params.sort) queryParams.set('sort', params.sort);
    if (params.search) queryParams.set('search', params.search);

    const query = queryParams.toString();
    return fetchAPI(`/chapters/novel/${slug}${query ? `?${query}` : ''}`);
}

export async function getChapterContent(slug, chapterNumber) {
    return fetchAPI(`/chapters/novel/${slug}/${chapterNumber}`);
}

// ================== Scraper API ==================

export async function startScraping(tocUrl, startChapter, endChapter = null) {
    const requestBody = {
        toc_url: tocUrl,
        start_chapter: startChapter,
    };

    // Only include end_chapter if provided - null triggers auto-detection
    if (endChapter !== null && endChapter !== '') {
        requestBody.end_chapter = endChapter;
    }

    return fetchAPI('/scraper/start', {
        method: 'POST',
        body: JSON.stringify(requestBody),
    });
}

export async function getScrapeStatus(jobId) {
    return fetchAPI(`/scraper/status/${jobId}`);
}

export async function listScrapeJobs() {
    return fetchAPI('/scraper/jobs');
}

export async function cancelScrapeJob(jobId) {
    return fetchAPI(`/scraper/cancel/${jobId}`, { method: 'POST' });
}

export async function removeScrapeJob(jobId) {
    return fetchAPI(`/scraper/job/${jobId}`, { method: 'DELETE' });
}

// ================== Audio API ==================

export async function getVoices() {
    return fetchAPI('/audio/voices');
}

export async function getAudioStatus(slug, chapterNumber) {
    return fetchAPI(`/audio/status/${slug}/${chapterNumber}`);
}

export async function getAudioHealth() {
    return fetchAPI('/audio/health');
}

export async function listAudioJobs(slug = null) {
    const query = slug ? `?novel_slug=${encodeURIComponent(slug)}` : '';
    return fetchAPI(`/audio/jobs${query}`);
}

export async function getNovelVoiceProfile(slug) {
    return fetchAPI(`/audio/profile/${slug}`);
}

export async function uploadNovelVoiceProfile(slug, { file, refText = '', displayName = '', voiceName = 'novel-default', language = 'English' }) {
    const form = new FormData();
    form.append('audio', file);
    form.append('ref_text', refText);
    form.append('display_name', displayName);
    form.append('voice_name', voiceName);
    form.append('language', language);

    return fetchAPI(`/audio/profile/${slug}`, {
        method: 'POST',
        body: form,
    });
}

export async function deleteNovelVoiceProfile(slug) {
    return fetchAPI(`/audio/profile/${slug}`, { method: 'DELETE' });
}

export async function generateChapterAudio(slug, chapterNumber, voice = 'af_heart') {
    return fetchAPI(`/audio/generate/${slug}/${chapterNumber}?voice=${voice}`, {
        method: 'POST',
    });
}

export function getAudioStreamUrl(slug, chapterNumber) {
    return `${API_BASE_URL}/audio/stream/${slug}/${chapterNumber}`;
}

export function getAudioTimingsUrl(slug, chapterNumber) {
    return `${API_BASE_URL}/audio/timings/${slug}/${chapterNumber}`;
}
