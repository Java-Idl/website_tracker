/**
 * Tracker.js
 * Captures user interactions and sends them to the local TUI client via Tailscale Funnel.
 */

const ENDPOINT = 'https://javagar-acer.tail9fdd55.ts.net/track';

// ---------------------------------------------------------
// Event Queue & Batching
// ---------------------------------------------------------

// Dual streams: One for general events, one for high-frequency continuous mouse data
let eventQueue = [];
let mouseQueue = [];

const GEN_FLUSH_INTERVAL_MS = 10000; // 10 seconds
const MOUSE_FLUSH_INTERVAL_MS = 3000; // 3 seconds

function queueEvent(eventType, data) {
    eventQueue.push({
        type: eventType,
        timestamp: Date.now(),
        ...data
    });
}

function queueMouseEvent(data) {
    mouseQueue.push({
        type: 'mousemove',
        timestamp: Date.now(),
        ...data
    });
}

// Helper: Compress string to gzip Blob
async function compressToGzipBlob(stringData) {
    const stream = new Blob([stringData]).stream();
    // Use the native CompressionStream API supported in modern browsers
    const compressedStream = stream.pipeThrough(new CompressionStream('gzip'));
    return await new Response(compressedStream).blob();
}

async function flushEvents(queueRef, label) {
    if (queueRef.length === 0) return;
    
    // Grabbing the current batch and resetting queue
    const batch = [...queueRef];
    // Clear the original array
    queueRef.length = 0;
    
    try {
        const jsonString = JSON.stringify(batch);
        const gzipBlob = await compressToGzipBlob(jsonString);

        // Always use fetch with keep-alive instead of sendBeacon. 
        // sendBeacon fails with CORS preflights when using non-safelisted Content-Types (like application/gzip or custom headers)
        fetch(ENDPOINT, {
            method: 'POST',
            mode: 'cors',
            headers: { 
                'Content-Encoding': 'gzip',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: gzipBlob,
            keepalive: true
        }).catch(err => console.error(`Tracker ${label} fetch error:`, err));
    } catch (e) {
        console.error(`Tracker ${label} batch flush error:`, e);
    }
}

// Start the distinct interval flushers
setInterval(() => flushEvents(eventQueue, 'general'), GEN_FLUSH_INTERVAL_MS);
setInterval(() => flushEvents(mouseQueue, 'mouse'), MOUSE_FLUSH_INTERVAL_MS);

// Flush before leaving the page just in case
window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
        flushEvents(eventQueue, 'general');
        flushEvents(mouseQueue, 'mouse');
    }
});

// ---------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------

// 1. Mouse Movement (Continuous, Unthrottled)
document.addEventListener('mousemove', (e) => {
    queueMouseEvent({ 
        x: e.clientX, 
        y: e.clientY,
        target: e.target.tagName + (e.target.id ? '#' + e.target.id : '')
    });
});

// 1b. Scroll Movement
window.addEventListener('scroll', () => {
    queueMouseEvent({
        type: 'scroll',
        y: window.scrollY || document.documentElement.scrollTop
    });
});

// 2. Clicks
document.addEventListener('click', (e) => {
    queueEvent('click', { 
        x: e.clientX, 
        y: e.clientY, 
        element: e.target.tagName,
        id: e.target.id || undefined,
        classes: e.target.className || undefined
    });
});

// 3. Keydown
document.addEventListener('keydown', (e) => {
    queueEvent('keydown', { 
        key: e.key,
        target: e.target.id || e.target.tagName
    });
});

// 4. Page View / Load
window.addEventListener('load', () => {
    queueEvent('pageview', {
        url: window.location.href,
        userAgent: navigator.userAgent
    });
});

console.log("Tracker successfully initialized. Listening to events...");
