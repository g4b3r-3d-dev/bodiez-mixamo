export type SettingsResponse = { blender_path: string | null; detected_path: string | null }
export type BlenderConnectionResult = { version: string; version_tuple: number[]; background: boolean; binary_path: string; python_version: string }
export type BoneNameAnalysis = { namespace_prefix: string | null; namespace_counts: Record<string, number>; semantic_matches: Record<string, string>; canonical_mixamo_matches: number; canonical_mixamo_total: number; canonical_match_ratio: number; likely_mixamo: boolean; note: string }
export type BoneInfo = { name: string; parent: string | null; children_count: number; deform: boolean; head_local: number[]; tail_local: number[]; length: number }
export type ArmatureInfo = { name: string; bone_count: number; roots: string[]; bones: BoneInfo[]; bone_name_analysis: BoneNameAnalysis }
export type ShapeKeyInfo = { name: string; value: number; min: number; max: number; basis: boolean }
export type WeightInfo = { armature: string | null; vertex_groups: number; bone_vertex_groups: number; weighted_vertices: number; total_vertices: number; coverage: number; average_influences: number; max_influences: number }
export type MeshInfo = { name: string; vertices: number; edges: number; polygons: number; materials: string[]; shape_keys: ShapeKeyInfo[]; armature: string | null; weights: WeightInfo }
export type MaterialInfo = { name: string; use_nodes: boolean; diffuse_color: number[] }
export type AnimationInfo = { actions: { name: string; frame_range: number[] }[]; nla_tracks: { armature: string; track: string; strips: string[] }[]; scene_frame_start: number; scene_frame_end: number; fps: number }
export type InspectionReport = { source: { name: string; format: string }; summary: { mesh_count: number; armature_count: number; material_count: number; shape_key_count: number; action_count: number; total_vertices: number; total_polygons: number; likely_mixamo: boolean }; scene: { object_count: number; unit_system: string; scale_length: number }; meshes: MeshInfo[]; armatures: ArmatureInfo[]; materials: MaterialInfo[]; animations: AnimationInfo; limitations: string[] }
export type AssetImportResult = { asset_id: string; original_name: string; preview_url: string; inspection: InspectionReport }
export type PreparationJointCheck = { semantic?: string; bone: string | null; passed: boolean; reason?: string | null; average_displacement?: number; test_pose_degrees?: number }
export type PreparationJointRegion = { passed: boolean; checks: PreparationJointCheck[] }
export type PreparationReport = {
  mode: 'existing_bound' | 'adapt_base'; ready_for_body_customization: boolean;
  target_rig: { armature: string; bone_count?: number; likely_mixamo: boolean; semantic_matches: Record<string, string>; core_matches?: number; core_total?: number };
  base_inspection: null | { before: { meshes: { name: string; vertices: number; polygons: number; shape_keys: string[]; shape_key_count: number; armature_modifiers: (string | null)[] }[]; armatures: { name: string; bone_count: number }[]; driver_count: number; mesh_count: number; armature_count: number; shape_key_count: number }; after: { driver_count: number; mesh_count: number; armature_count: number; shape_key_count: number; meshes: unknown[]; armatures: unknown[] }; conflicting_armatures: { mesh: string; armature: string }[] };
  alignment: { performed: boolean; reference_pose: string; auto_scale?: number; user_scale?: number; total_scale?: number; offset?: number[]; rotation_z_degrees?: number; note?: string };
  binding: { already_bound: boolean; weight_transfer_performed: boolean; weight_transfer_is_retargeting: boolean; method?: string; meshes?: { mesh: string; coverage: number; weighted_vertices: number; total_vertices: number }[]; transfers?: { mesh?: string; performed: boolean; method?: string; coverage?: number; assigned_vertices?: number; total_vertices?: number; mean_reference_distance?: number | null; reason?: string; note?: string }[] };
  preservation: { topology_preserved: boolean; shape_keys_preserved?: number; shape_keys_before?: number; shape_keys_after?: number; drivers_before?: number; drivers_after?: number; destructive_modifiers_applied: boolean };
  joint_validation: { all_passed: boolean; regions: Record<string, PreparationJointRegion> }; blockers: string[]; warnings: string[]; limitations: string[];
}
export type PreparationResult = { asset_id: string; preparation_id: string; mode: 'existing_bound' | 'adapt_base'; preview_url: string; blend_url: string; preparation: PreparationReport }
export type AdaptBaseOptions = { scale: number; offset_x: number; offset_y: number; offset_z: number; rotation_z: number }
export type TaskResult = BlenderConnectionResult | AssetImportResult | PreparationResult
export type TaskEvent = { type: 'progress'; value: number; message: string } | { type: 'log'; level: 'info' | 'warning' | 'error'; stream: string; message: string } | { type: 'success'; message: string; result: TaskResult } | { type: 'error'; message: string; code: string }
export function isBlenderConnectionResult(result: TaskResult): result is BlenderConnectionResult { return 'version' in result && 'python_version' in result }
export function isAssetImportResult(result: TaskResult): result is AssetImportResult { return 'asset_id' in result && 'inspection' in result }
export function isPreparationResult(result: TaskResult): result is PreparationResult { return 'preparation_id' in result && 'preparation' in result }
