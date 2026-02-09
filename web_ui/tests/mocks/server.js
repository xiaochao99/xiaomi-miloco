/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

// Default handlers placeholder; extend per test via server.use(...)
export const handlers = [
	// Example: http.get('/api/health', () => HttpResponse.json({ ok: true }))
];

export const server = setupServer(...handlers);

