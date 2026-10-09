const id = '6ba7b810-9dad-41d1-80b4-00c04fd430c8';
const assetId = '6ba7b810-9dad-41d1-80b4-00c04fd430c9';
const completedAssetId = '6ba7b810-9dad-41d1-80b4-00c04fd430ca';
const date = '2026-10-01T12:00:00Z';
const card = { id, kind: 'text', status: 'ready', capturedAt: date, sourceApp: null, sourceUrl: null, sourceDomain: null, title: 'Synthetic' };
const detail = { ...card, processingError: null, description: null, userNote: null, contentText: 'Synthetic', pageText: null, captureMetadata: {}, occurredAt: null, createdAt: date, updatedAt: date, spaces: [], tags: [], assets: [] };
module.exports = { id, assetId, completedAssetId, date, card, detail };
