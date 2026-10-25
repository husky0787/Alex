function handler(event) {
    var request = event.request;
    var uri = request.uri;
    // This function belongs only to the static-origin behavior.
    if ((request.method !== 'GET' && request.method !== 'HEAD') ||
        uri === '/api' || uri.indexOf('/api/') === 0 || uri.indexOf('/_next/') === 0) {
        return request;
    }
    if (uri === '/') {
        request.uri = '/index.html';
        return request;
    }
    uri = uri.replace(/\/$/, '');
    // Next.js Pages Router exports one shell for the client-side account route.
    if (/^\/accounts\/[^/.]+$/.test(uri)) {
        request.uri = '/accounts/%5Bid%5D.html';
    } else if (uri.indexOf('.') === -1) {
        request.uri = uri + '.html';
    }
    return request;
}
