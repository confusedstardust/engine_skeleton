const test = require('node:test');
const assert = require('node:assert/strict');
const React = require('../forge_frontend_next/node_modules/react');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { hookHarness } = require('./helpers/hook_harness.cjs');
const {
  validateUpload,
  imageUploadPolicy: image,
  musicUploadPolicy: music,
  adminMusicUploadPolicy: adminMusic,
} = loadFrontendTs('forge_frontend_next/lib/upload-policy.ts');
const file = (name = 'music.mp3', size = 100) => ({ name, size });
function all(node, type) {
  if (Array.isArray(node)) return node.flatMap((child) => all(child, type));
  if (!node || typeof node !== 'object' || !node.props) return [];
  return [...(node.type === type ? [node] : []), ...all(node.props.children, type)];
}
const deferred = () => {
  let resolve;
  const promise = new Promise((r) => (resolve = r));
  return { promise, resolve };
};

test('upload policy handles empty/oversize files, uppercase extensions, and distinct endpoint formats', () => {
  assert.match(validateUpload(file('empty.mp3', 0), music), /不能为空/);
  assert.match(validateUpload(file('large.mp3', music.maxBytes + 1), music), /30 MB/);
  assert.equal(validateUpload(file('edge.MP3', music.maxBytes), music), null);
  assert.equal(validateUpload(file('photo.JPEG'), image), null);
  assert.equal(validateUpload(file('track.m4a'), adminMusic), null);
  assert.match(validateUpload(file('track.m4a'), music), /格式/);
  assert.match(validateUpload(file('disguised.mp3.exe'), music), /格式/);
});

test('upload execution blocks duplicate submission and allows retry after server failure', async () => {
  const h = hookHarness();
  const { useFileUpload } = loadFrontendTs('forge_frontend_next/hooks/use-file-upload.ts', { react: h.react });
  const render = () => h.render(useFileUpload);
  render();
  const wait = deferred();
  let calls = 0;
  const task = () => {
    calls++;
    return wait.promise;
  };
  const first = render().run(file(), music, task);
  assert.equal(render().pending, true);
  assert.equal(await render().run(file(), music, task), false);
  assert.equal(calls, 1);
  wait.resolve(false);
  assert.equal(await first, false);
  assert.match(render().error, /上传失败/);
  assert.equal(
    await render().run(file(), music, async () => {
      throw new Error('HTTP 413');
    }),
    false,
  );
  assert.equal(render().error, 'HTTP 413');
  assert.equal(render().pending, false);
  assert.equal(await render().run(file(), music, async () => true), true);
  assert.equal(render().error, '');
  h.unmount();
});

test('invalid uploads never call the backend and unmounted uploads do not update state', async () => {
  const h = hookHarness();
  const { useFileUpload } = loadFrontendTs('forge_frontend_next/hooks/use-file-upload.ts', { react: h.react });
  const render = () => h.render(useFileUpload);
  render();
  let calls = 0;
  await render().run(file('bad.exe'), music, async () => {
    calls++;
  });
  assert.equal(calls, 0);
  const wait = deferred();
  const request = render().run(file(), music, () => wait.promise);
  h.unmount();
  wait.resolve(false);
  await request;
  assert.equal(render().error, '');
});

test('late upload success cannot trigger success actions after leaving the page', async () => {
  const h = hookHarness();
  const { useFileUpload } = loadFrontendTs('forge_frontend_next/hooks/use-file-upload.ts', { react: h.react });
  const render = () => h.render(useFileUpload);
  render();
  const wait = deferred();
  const request = render().run(file(), music, () => wait.promise);
  h.unmount();
  wait.resolve(true);
  assert.equal(await request, false);
});

test('file picker captures the input before await and resets for selecting the same file again', async () => {
  const { AssetFileInput } = loadFrontendTs('forge_frontend_next/components/ui/file-upload.tsx');
  const wait = deferred(),
    errors = [],
    input = { files: [file()], value: 'music.mp3' };
  const node = AssetFileInput.render(
    {
      policy: music,
      resetAfterSelect: true,
      onFileSelected: () => wait.promise,
      onValidationError: (x) => errors.push(x),
    },
    null,
  );
  const event = { currentTarget: input };
  const request = node.props.onChange(event);
  event.currentTarget = null;
  wait.resolve();
  await request;
  assert.equal(input.value, '');
  assert.deepEqual(errors, ['']);
  input.value = 'bad.exe';
  input.files = [file('bad.exe')];
  await node.props.onChange({ currentTarget: input });
  assert.equal(input.value, '');
  assert.match(errors.at(-1), /格式/);
});

test('pagination preserves boundaries, loading state, and offset adapters', () => {
  const { Pagination } = loadFrontendTs('forge_frontend_next/components/ui/pagination.tsx');
  let offset;
  let tree = Pagination({ page: 1, hasMore: true, onPageChange: (page) => (offset = (page - 1) * 20) });
  let buttons = all(tree, 'button');
  assert.equal(buttons[0].props.disabled, true);
  buttons[1].props.onClick();
  assert.equal(offset, 20);
  assert.equal(buttons[1].props.type, 'button');
  tree = Pagination({ page: 3, hasMore: false, disabled: true, onPageChange: () => {} });
  assert.ok(all(tree, 'button').every((b) => b.props.disabled));
});

test('preview renders lazy images, playable audio, and noninteractive audio inside selectable options', () => {
  const SharedImage = () => null;
  const { AssetPreview } = loadFrontendTs('forge_frontend_next/components/assets/asset-preview.tsx', {
    '../ui/image-preview': { ImagePreview: SharedImage },
    './audio-preview': { AudioPreview: () => null },
  });
  const base = { url: '/file', name: 'preview' };
  const imageNode = AssetPreview({ asset: { ...base, mime_type: 'image/png' }, decorative: true });
  assert.equal(imageNode.type, SharedImage);
  assert.equal(imageNode.props.alt, '');
  assert.equal(imageNode.props.loading, 'lazy');
  const selectable = AssetPreview({
    asset: { ...base, mime_type: 'audio/mpeg' },
    interactive: false,
    decorative: true,
  });
  assert.equal(selectable.type, 'span');
  assert.equal(selectable.props['aria-hidden'], true);
  assert.equal(typeof AssetPreview({ asset: { ...base, mime_type: 'audio/mpeg' } }).type, 'function');
});

test('tooltips keep enabled button as trigger and wrap disabled buttons for keyboard access', () => {
  const { ActionHint } = loadFrontendTs('forge_frontend_next/components/ui/action-hint.tsx');
  const enabled = React.createElement('button', { disabled: false }, 'run');
  const disabled = React.createElement('button', { disabled: true }, 'run');
  assert.equal(all(ActionHint({ text: 'hint', children: enabled }), 'span').length, 0);
  assert.equal(all(ActionHint({ text: 'hint', children: disabled }), 'span')[0].props.tabIndex, 0);
  assert.equal(ActionHint({ children: enabled }).props.children, enabled);
});


test('shared image replaces failed resources and keys loading state by image address', () => {
  const harness = hookHarness();
  const { ImagePreview } = loadFrontendTs('forge_frontend_next/components/ui/image-preview.tsx', { react: { ...React, ...harness.react } });
  const first = ImagePreview({ src: '/old.webp', alt: 'cover', fallback: '无封面' });
  let rendered = harness.render(() => first.type(first.props));
  assert.equal(rendered.type, 'img');
  rendered.props.onError({});
  rendered = harness.render(() => first.type(first.props));
  assert.equal(rendered.type, 'span');
  assert.equal(rendered.props.children, '无封面');
  const next = ImagePreview({ src: '/new.webp', fallback: '无封面' });
  assert.notEqual(next.key, first.key);
  const fresh = hookHarness();
  const image = loadFrontendTs('forge_frontend_next/components/ui/image-preview.tsx', { react: { ...React, ...fresh.react } }).ImagePreview({ src: '/new.webp' });
  assert.equal(fresh.render(() => image.type(image.props)).type, 'img');
});


test('Button defaults to non-submit and centralizes busy, disabled, style and forwarded refs', () => {
  const { Button } = loadFrontendTs('forge_frontend_next/components/ui/button.tsx');
  const ref = React.createRef();
  const defaults = Button.render({ children: '关闭' }, ref);
  assert.equal(defaults.type, 'button');
  assert.equal(defaults.props.type, 'button');
  assert.equal(defaults.props.className, 'btn outline');
  assert.equal(defaults.props.ref, ref);
  const busy = Button.render({ type: 'submit', variant: 'primary', busy: true, disabled: false, className: 'custom' }, ref);
  assert.equal(busy.props.disabled, true);
  assert.equal(busy.props['aria-busy'], true);
  assert.equal(busy.props.type, 'submit');
  assert.equal(busy.props.className, 'btn primary custom');
  assert.equal(Button.render({ disabled: true }, ref).props.disabled, true);
  assert.equal(Button.render({ 'aria-busy': 'true' }, ref).props.disabled, true);
});
