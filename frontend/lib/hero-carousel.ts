import type { HeroSlide } from './api/types';

export function heroImages(slides: HeroSlide[], mobile: boolean) {
  return slides.flatMap(slide => (mobile ? slide.mobile_image : slide.image) ?? []);
}
export function slideIsEager(index: number, current: number, length: number) {
  return index === 0 || index === current || index === (current + 1) % length;
}
