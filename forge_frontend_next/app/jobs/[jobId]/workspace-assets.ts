import type { AssetReviewItem } from '../../../domain/assets';
export function assetDisplayName(asset: AssetReviewItem) {
  if (asset.display_name) return asset.display_name;
  return asset.filename
    .replace(/^figure_/, '')
    .replace(/^bg_/, '')
    .replace(/^title_/, '')
    .replace(/_/g, ' ');
}

export function assetSceneDisplayName(asset: AssetReviewItem) {
  return asset.scene_display_name || asset.available_scene || '通用';
}
