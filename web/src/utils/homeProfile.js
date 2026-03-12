export const HOME_PROFILE_STORAGE_KEY = 'novellabs.homeProfile';

export const DEFAULT_HOME_PROFILE = {
    displayName: 'Reader',
    creditUrl: 'https://github.com/MohitRawat017/NovelLabs',
};

export function getHomeProfile() {
    try {
        const saved = localStorage.getItem(HOME_PROFILE_STORAGE_KEY);
        const parsed = saved ? JSON.parse(saved) : {};
        return {
            ...DEFAULT_HOME_PROFILE,
            ...parsed,
        };
    } catch {
        return DEFAULT_HOME_PROFILE;
    }
}

export function saveHomeProfile(profile) {
    const normalized = {
        displayName: (profile.displayName || 'Reader').trim() || 'Reader',
        creditUrl: (profile.creditUrl || DEFAULT_HOME_PROFILE.creditUrl).trim() || DEFAULT_HOME_PROFILE.creditUrl,
    };
    localStorage.setItem(HOME_PROFILE_STORAGE_KEY, JSON.stringify(normalized));
    return normalized;
}

export function getAvatarUrl(profile) {
    const seed = `${profile.displayName || 'Reader'}-${profile.creditUrl || ''}`;
    return `https://api.dicebear.com/7.x/notionists/svg?seed=${encodeURIComponent(seed)}&backgroundColor=f5f5f4,b39ddb,0f172a`;
}
