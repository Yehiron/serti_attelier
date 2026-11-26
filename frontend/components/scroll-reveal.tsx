'use client';

import { useEffect } from 'react';
import { installScrollReveal } from '@/lib/scroll-reveal';

export function ScrollReveal() {
  useEffect(() => installScrollReveal(document, window), []);
  return null;
}
