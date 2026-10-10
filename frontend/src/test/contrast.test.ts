import { describe, expect, it } from 'vitest';
import css from '../styles.css?raw';

// WCAG 2.1 AA para texto normal: 4,5:1 em toda a interface (o texto fica entre 13 e 32 px).
const AA = 4.5;

const root = css.slice(css.indexOf(':root {'), css.indexOf('}', css.indexOf(':root {')));
const tokens = Object.fromEntries([...root.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{3,6})/g)].map((match) => [match[1], match[2]]));
const color = (name: string) => {
  if (!tokens[name]) throw new Error(`Token ausente: --${name}`);
  return tokens[name];
};

function rule(selector: string, property: 'color' | 'background') {
  const block = css.match(new RegExp(`(?:^|\\n)${selector.replace(/[.]/g, '\\.')}\\s*\\{([^}]*)\\}`))?.[1] ?? '';
  const value = block.match(new RegExp(`(?:^|;)\\s*${property}:\\s*([^;]+)`))?.[1].trim() ?? '';
  const token = value.match(/var\(--([\w-]+)\)/)?.[1];
  if (!token) throw new Error(`Cor não resolvida em ${selector}: ${value}`);
  return color(token);
}

function luminance(hex: string) {
  const value = hex.length === 4 ? hex.slice(1).split('').map((c) => c + c).join('') : hex.slice(1);
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(foreground: string, background: string) {
  const [a, b] = [luminance(foreground), luminance(background)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

const PAIRS: Array<[string, string, string]> = [
  ['tinta sobre papel', color('ink'), color('paper')],
  ['tinta sobre folha', color('ink'), color('sheet')],
  ['texto secundário sobre papel', color('graphite'), color('paper')],
  ['texto secundário sobre folha', color('graphite'), color('sheet')],
  ['texto secundário sobre tinta clara', color('graphite'), color('tint')],
  ['link e ação sobre papel', color('pen'), color('paper')],
  ['link e ação sobre folha', color('pen'), color('sheet')],
  ['link e ação sobre azul claro', color('pen'), color('pen-tint')],
  ['botão primário', '#ffffff', color('pen')],
  ['posição de destaque na fila', color('paper'), color('ink')],
  ['menu sobre a faixa de tinta', color('ink-muted'), color('ink')],
  ['aba ativa do menu (recorte de papel)', color('ink'), color('paper')],
  ['texto secundário na barra do celular', color('ink-muted'), color('ink-2')],
  ['botões na barra do celular', color('paper'), color('ink-2')],
  ['urgente sobre folha', color('urgent'), color('sheet')],
  ['urgente sobre fundo urgente', color('urgent'), color('urgent-tint')],
  ['revisar sobre folha', color('review'), color('sheet')],
  ['revisar sobre fundo de revisão', color('review'), color('review-tint')],
  ['ok sobre fundo ok', color('ok'), color('ok-tint')],
  ['selo crítico', rule('.badge-critical, .badge-high', 'color'), rule('.badge-critical, .badge-high', 'background')],
  ['selo médio', rule('.badge-medium, .badge-low', 'color'), rule('.badge-medium, .badge-low', 'background')],
  ['selo bom', rule('.badge-good', 'color'), rule('.badge-good', 'background')],
  ['selo informativo', rule('.badge-info', 'color'), rule('.badge-info', 'background')],
  ['selo neutro', rule('.badge-neutral', 'color'), rule('.badge-neutral', 'background')],
];

describe('contraste de cores (WCAG AA)', () => {
  it.each(PAIRS)('%s', (_name, foreground, background) => {
    expect(contrast(foreground, background)).toBeGreaterThanOrEqual(AA);
  });

  it('calcula razões de referência corretamente', () => {
    expect(contrast('#000000', '#ffffff')).toBeCloseTo(21, 1);
    expect(contrast('#777777', '#ffffff')).toBeCloseTo(4.48, 1);
    expect(contrast('#718096', '#ffffff')).toBeLessThan(AA);
  });
});
