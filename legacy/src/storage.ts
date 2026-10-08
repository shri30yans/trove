import {
  GetObjectCommand,
  HeadBucketCommand,
  HeadObjectCommand,
  PutObjectCommand,
  S3Client,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { randomUUID } from 'node:crypto';
import { config } from './config.js';

const clientOptions = (endpoint: string) => ({
  endpoint,
  region: config.S3_REGION,
  forcePathStyle: config.S3_FORCE_PATH_STYLE,
  credentials: { accessKeyId: config.S3_ACCESS_KEY, secretAccessKey: config.S3_SECRET_KEY },
});

const internalClient = new S3Client(clientOptions(config.S3_ENDPOINT));
const signingClient = new S3Client(clientOptions(config.S3_PUBLIC_ENDPOINT));

export async function ensureBucket() {
  await internalClient.send(new HeadBucketCommand({ Bucket: config.S3_BUCKET }));
}

export function newObjectKey(userId: string, filename: string) {
  const extension = filename.includes('.') ? filename.split('.').pop()!.toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 12) : '';
  const suffix = extension ? `.${extension}` : '';
  const date = new Date();
  return `${userId}/${date.getUTCFullYear()}/${String(date.getUTCMonth() + 1).padStart(2, '0')}/${randomUUID()}${suffix}`;
}

export async function createUploadUrl(objectKey: string, mimeType: string) {
  const command = new PutObjectCommand({
    Bucket: config.S3_BUCKET,
    Key: objectKey,
    ContentType: mimeType,
  });
  return getSignedUrl(signingClient, command, { expiresIn: config.UPLOAD_URL_TTL_SECONDS });
}

export async function createReadUrl(objectKey: string) {
  return getSignedUrl(
    signingClient,
    new GetObjectCommand({ Bucket: config.S3_BUCKET, Key: objectKey }),
    { expiresIn: 900 },
  );
}

export async function headObject(objectKey: string) {
  return internalClient.send(new HeadObjectCommand({ Bucket: config.S3_BUCKET, Key: objectKey }));
}

export async function readObject(objectKey: string) {
  const result = await internalClient.send(new GetObjectCommand({ Bucket: config.S3_BUCKET, Key: objectKey }));
  if (!result.Body) throw new Error('Stored asset body is empty');
  return Buffer.from(await result.Body.transformToByteArray());
}
