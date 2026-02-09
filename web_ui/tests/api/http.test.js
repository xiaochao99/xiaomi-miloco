/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { getApi, postApi, putApi, deleteApi } from '@/utils/http';

vi.mock('antd', () => ({
  message: {
    destroy: vi.fn(),
    error: vi.fn()
  }
}));

beforeEach(() => {
  delete window.location;
  // @ts-ignore
  window.location = new URL('http://localhost/');
});

describe('utils/http', () => {
  it('success request return data', async () => {
    server.use(
      http.get('/api/test-success', () => HttpResponse.json({ ok: true, value: 1 }, { status: 200 }))
    );
    const res = await getApi('/api/test-success');
    expect(res).toEqual({ ok: true, value: 1 });
  });

  it('4xx return null and show error message', async () => {
    const { message } = await import('antd');
    server.use(
      http.get('/api/test-400', () => HttpResponse.json({ message: 'bad request' }, { status: 400 }))
    );
    const res = await getApi('/api/test-400');
    expect(res).toBeNull();
    expect(message.error).toHaveBeenCalledWith('bad request');
  });

  it('401 redirect to /login', async () => {
    server.use(
      http.get('/api/test-401', () => HttpResponse.json({ message: 'unauthorized' }, { status: 401 }))
    );
    const res = await getApi('/api/test-401');
    expect(res).toBeNull();
    expect(window.location.href).toContain('/login');
  });

  it('500 redirect to /500', async () => {
    server.use(
      http.get('/api/test-500', () => HttpResponse.json({ message: 'server error' }, { status: 500 }))
    );
    const res = await getApi('/api/test-500');
    expect(res).toBeNull();
    expect(window.location.href).toContain('/500');
  });

  it('GET parameters should be appended to URL query', async () => {
    server.use(
      http.get('/api/echo', ({ request }) => {
        const url = new URL(request.url);
        return HttpResponse.json({ search: url.search }, { status: 200 });
      })
    );
    const res = await getApi('/api/echo', { a: 1, b: 'x' });
    expect(res.search).toMatch(/a=1/);
    expect(res.search).toMatch(/b=x/);
  });

  it('POST parameters should be in request body', async () => {
    server.use(
      http.post('/api/echo', async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ body }, { status: 200 });
      })
    );
    const res = await postApi('/api/echo', { a: 1, b: 'y' });
    expect(res.body).toEqual({ a: 1, b: 'y' });
  });

  it('PUT parameters should be in request body', async () => {
    server.use(
      http.put('/api/echo', async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ body }, { status: 200 });
      })
    );
    const res = await putApi('/api/echo', { a: 2, b: 'z' });
    expect(res.body).toEqual({ a: 2, b: 'z' });
  });

  it('DELETE should return data successfully (no request body)', async () => {
    server.use(
      http.delete('/api/item/123', () => HttpResponse.json({ ok: true }, { status: 200 }))
    );
    const res = await deleteApi('/api/item/123');
    expect(res).toEqual({ ok: true });
  });
});

