/**
 * API Service - handles all backend API calls
 */

const API_BASE_URL = 'http://localhost:8001/api';

/**
 * Generic fetch wrapper with error handling
 */
async function fetchAPI(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;

    const response = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
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

export async function updateNovel(slug) {
    return fetchAPI(`/novels/${slug}/update`, { method: 'POST' });
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

export function getAudioUrl(slug, chapterNumber) {
    return `${API_BASE_URL}/audio/novel/${slug}/${chapterNumber}`;
}

export async function generateAudio(chapterId, voice = 'af_heart') {
    return fetchAPI(`/audio/generate/${chapterId}?voice=${voice}`, {
        method: 'POST',
    });
}
