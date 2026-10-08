import { useEffect, useRef } from 'react';
import Constants from 'expo-constants';
import { useRouter } from 'expo-router';
import { useShareIntent } from 'expo-share-intent';
import type { CaptureAttachment, MemoryCapture } from '../../types';

export function useShareIntentCapture(saveCapture: (capture: MemoryCapture) => Promise<boolean>, showToast: (message: string) => void) {
  const router = useRouter();
  const expoGo = Constants.executionEnvironment === 'storeClient';
  const { hasShareIntent, shareIntent, resetShareIntent } = useShareIntent({ disabled: expoGo, scheme: 'trove' });
  const handledShare = useRef(false);

  useEffect(() => {
    if (!hasShareIntent || handledShare.current) return;
    handledShare.current = true;
    void (async () => {
      try {
        const files = shareIntent.files || [];
        const rawText = (shareIntent.text || '').trim();
        const sharedUrl = shareIntent.webUrl || rawText.match(/https?:\/\/[^\s]+/i)?.[0] || '';
        const meta = shareIntent.meta || {};
        if (files.length) {
          const attachments: CaptureAttachment[] = files.map((file) => {
            const mimeType = file.mimeType || 'application/octet-stream';
            const kind = mimeType.startsWith('image/') ? 'image' : mimeType.startsWith('video/') ? 'video' : mimeType.startsWith('audio/') ? 'audio' : 'file';
            return {
              kind,
              title: file.fileName || undefined,
              sourceApp: 'Shared from another app',
              captureMetadata: { shareIntent: true, sharedType: shareIntent.type },
              asset: { uri: file.path, filename: file.fileName || `shared-${Date.now()}`, mimeType, byteSize: file.size || undefined },
            };
          });
          const contentText = [rawText, meta.description].filter(Boolean).join('\n\n');
          await saveCapture({
            kind: attachments[0]?.kind || 'file', title: meta.title || attachments[0]?.title,
            description: meta.description, contentText: contentText || undefined,
            sourceUrl: sharedUrl || undefined, sourceApp: 'Shared from another app',
            captureMetadata: { shareIntent: true, sharedType: shareIntent.type }, attachments,
          });
        } else if (sharedUrl) {
          await saveCapture({
            kind: 'link', sourceUrl: sharedUrl, title: meta.title,
            description: meta.description, contentText: rawText || undefined,
            sourceApp: 'Shared from another app', captureMetadata: { shareIntent: true, shareMeta: meta },
          });
        } else if (rawText || meta.title) {
          const text = rawText || meta.title || '';
          await saveCapture({ kind: 'text', title: text.split('\n')[0]?.slice(0, 120), userNote: text, contentText: text, sourceApp: 'Shared from another app', captureMetadata: { shareIntent: true } });
        } else {
          showToast('Trove did not receive anything to save.');
        }
        router.replace('/');
      } catch (error) {
        showToast(error instanceof Error ? error.message : 'Could not save the shared item.');
      } finally {
        resetShareIntent();
        handledShare.current = false;
      }
    })();
  }, [hasShareIntent, shareIntent, resetShareIntent, saveCapture, showToast, router]);
}
