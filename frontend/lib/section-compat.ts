import type { Section } from './api/sections.generated.ts';
import { sectionKinds } from './api/sections.generated.ts';

/** Keep unknown future kinds out of server rendering, even with mixed deployments. */
export function supportedSections(sections: Section[]): Section[] {
  return sections.filter(section => {
    if (!(sectionKinds as readonly string[]).includes(section.kind) || (section.schema_version !== undefined && section.schema_version !== 1)) {
      console.warn('Se omite una sección CMS desconocida:', section.kind, section.schema_version);
      return false;
    }
    return true;
  });
}
