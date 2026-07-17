/** Exporta el primer <svg> (gráfica Recharts) dentro de un contenedor a PNG,
 * client-side, sin librerías nuevas (F7, ChartCard 2.0). Serializa el SVG a un
 * blob, lo dibuja en un canvas del tamaño real del elemento y descarga el PNG. */
export const exportSvgAsPng = async (container: HTMLElement, filename: string) => {
  const svg = container.querySelector('svg');
  if (!svg) return;

  const rect = svg.getBoundingClientRect();
  const clone = svg.cloneNode(true) as SVGElement;
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('width', String(rect.width));
  clone.setAttribute('height', String(rect.height));

  const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  bgRect.setAttribute('width', '100%');
  bgRect.setAttribute('height', '100%');
  bgRect.setAttribute('fill', '#171F31');
  clone.insertBefore(bgRect, clone.firstChild);

  const svgString = new XMLSerializer().serializeToString(clone);
  const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(svgBlob);

  const img = new Image();
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = reject;
    img.src = url;
  });

  const scale = 2;
  const canvas = document.createElement('canvas');
  canvas.width = rect.width * scale;
  canvas.height = rect.height * scale;
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    URL.revokeObjectURL(url);
    return;
  }
  ctx.scale(scale, scale);
  ctx.drawImage(img, 0, 0, rect.width, rect.height);
  URL.revokeObjectURL(url);

  canvas.toBlob((blob) => {
    if (!blob) return;
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${filename}.png`;
    link.click();
    URL.revokeObjectURL(link.href);
  }, 'image/png');
};
