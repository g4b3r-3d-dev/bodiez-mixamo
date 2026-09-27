from __future__ import annotations
import argparse, json, math, re, sys, traceback
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

RESULT_PREFIX='BODIEZ_RESULT:'
SEM={
'hips':{'hips','pelvis'},'head':{'head'},
'left_upper_arm':{'leftarm','leftupperarm','lupperarm','upperarml'},'right_upper_arm':{'rightarm','rightupperarm','rupperarm','upperarmr'},
'left_forearm':{'leftforearm','leftlowerarm','lforearm','lowerarml'},'right_forearm':{'rightforearm','rightlowerarm','rforearm','lowerarmr'},
'left_thigh':{'leftupleg','leftthigh','lthigh','thighl'},'right_thigh':{'rightupleg','rightthigh','rthigh','thighr'},
'left_shin':{'leftleg','leftlowerleg','lshin','calfl'},'right_shin':{'rightleg','rightlowerleg','rshin','calfr'},
'left_foot':{'leftfoot','lfoot','footl'},'right_foot':{'rightfoot','rfoot','footr'}}
JOINTS={'shoulders':['left_upper_arm','right_upper_arm'],'elbows':['left_forearm','right_forearm'],'hips':['left_thigh','right_thigh'],'knees':['left_shin','right_shin']}

def args():
    p=argparse.ArgumentParser(add_help=False); p.add_argument('--mode',choices=('existing_bound','adapt_base'),required=True)
    for n in ('source','preview','blend','report'): p.add_argument('--'+n,required=True)
    p.add_argument('--base'); p.add_argument('--scale',type=float,default=1.0)
    for n in ('offset-x','offset-y','offset-z','rotation-z'): p.add_argument('--'+n,type=float,default=0.0)
    return p.parse_args(sys.argv[sys.argv.index('--')+1:])

def norm(n):
    n=n.replace('\\','/').split('/')[-1].split('|')[-1].rsplit(':',1)[-1]
    n=re.sub(r'[^A-Za-z0-9]','',n)
    return n[len('mixamorig'):] if n.lower().startswith('mixamorig') else n

def rig_info(a):
    lookup={norm(b.name).lower():b.name for b in a.data.bones}; matches={}
    for key,vars in SEM.items():
        for v in vars:
            if v in lookup: matches[key]=lookup[v]; break
    return {'armature':a.name,'bone_count':len(a.data.bones),'semantic_matches':matches,'likely_mixamo':len(matches)>=10,'core_matches':len(matches),'core_total':len(SEM)}

def import_model(path):
    before=set(bpy.data.objects); ext=path.suffix.lower()
    if ext=='.fbx': bpy.ops.import_scene.fbx(filepath=str(path))
    elif ext in {'.glb','.gltf'}: bpy.ops.import_scene.gltf(filepath=str(path))
    else: raise RuntimeError('Formato de personagem não suportado.')
    return [o for o in bpy.data.objects if o.name not in before]

def import_base(path):
    if path.suffix.lower()!='.blend': return import_model(path)
    with bpy.data.libraries.load(str(path),link=False) as (src,dst): dst.objects=list(src.objects)
    out=[]
    for o in dst.objects:
        if o and not o.users_collection: bpy.context.scene.collection.objects.link(o)
        if o: out.append(o)
    return out

def mesh_rig(m):
    for md in m.modifiers:
        if md.type=='ARMATURE' and md.object: return md.object
    return m.parent if m.parent and m.parent.type=='ARMATURE' else None

def coverage(m,a):
    bones={b.name for b in a.data.bones}; ids={g.index for g in m.vertex_groups if g.name in bones}; weighted=infs=0
    for v in m.data.vertices:
        c=sum(1 for e in v.groups if e.group in ids and e.weight>1e-6)
        weighted+=bool(c); infs+=c
    total=len(m.data.vertices)
    return {'mesh':m.name,'weighted_vertices':weighted,'total_vertices':total,'coverage':round(weighted/total,5) if total else 0,'average_influences':round(infs/weighted,3) if weighted else 0}

def inspect(objs):
    meshes=[]; drivers=0; arms=[]
    for o in objs:
        ad=getattr(o,'animation_data',None); drivers+=len(ad.drivers) if ad else 0
        if o.type=='ARMATURE': arms.append({'name':o.name,'bone_count':len(o.data.bones)})
        if o.type!='MESH': continue
        keys=[k.name for k in o.data.shape_keys.key_blocks] if o.data.shape_keys else []
        kd=getattr(o.data.shape_keys,'animation_data',None) if o.data.shape_keys else None; drivers+=len(kd.drivers) if kd else 0
        meshes.append({'name':o.name,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons),'shape_keys':keys,'shape_key_count':max(0,len(keys)-1),'armature_modifiers':[m.object.name if m.object else None for m in o.modifiers if m.type=='ARMATURE']})
    return {'meshes':meshes,'armatures':arms,'mesh_count':len(meshes),'armature_count':len(arms),'shape_key_count':sum(x['shape_key_count'] for x in meshes),'driver_count':drivers}

def bounds(meshes):
    pts=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
    if not pts: raise RuntimeError('Sem geometria para alinhamento.')
    return Vector(tuple(min(p[i] for p in pts) for i in range(3))),Vector(tuple(max(p[i] for p in pts) for i in range(3)))

def align(base,ref,a):
    bmin,bmax=bounds(base); rmin,rmax=bounds(ref); bh=max(bmax.z-bmin.z,1e-8); rh=max(rmax.z-rmin.z,1e-8)
    s=(rh/bh)*a.scale; bc=(bmin+bmax)*.5; rc=(rmin+rmax)*.5+Vector((a.offset_x,a.offset_y,a.offset_z))
    root=bpy.data.objects.new('Bodiez_BaseAlignment',None); bpy.context.scene.collection.objects.link(root); base_set=set(base)
    for o in base:
        if o.parent not in base_set:
            w=o.matrix_world.copy(); o.parent=root; o.matrix_world=w
    root.matrix_world=Matrix.Translation(rc)@Matrix.Rotation(math.radians(a.rotation_z),4,'Z')@Matrix.Diagonal((s,s,s,1))@Matrix.Translation(-bc)
    bpy.context.view_layer.update()
    return root,{'performed':True,'reference_pose':'target_armature_rest_pose','auto_scale':round(rh/bh,6),'user_scale':a.scale,'total_scale':round(s,6),'offset':[a.offset_x,a.offset_y,a.offset_z],'rotation_z_degrees':a.rotation_z,'note':'Alinhamento global; diferenças locais de pose/proporção exigem revisão assistida.'}

def transfer(src,dst,arm):
    names={g.index:g.name for g in src.vertex_groups}; bones={b.name for b in arm.data.bones}; valid={i for i,n in names.items() if n in bones}
    if not valid: return {'mesh':dst.name,'performed':False,'reason':'Referência sem grupos de ossos utilizáveis.'}
    kd=KDTree(len(src.data.vertices))
    for v in src.data.vertices: kd.insert(src.matrix_world@v.co,v.index)
    kd.balance()
    for g in list(dst.vertex_groups):
        if g.name in bones: dst.vertex_groups.remove(g)
    assigned=0; dists=[]
    for v in dst.data.vertices:
        _,idx,dist=kd.find(dst.matrix_world@v.co); sv=src.data.vertices[idx]; vals=[(names[e.group],e.weight) for e in sv.groups if e.group in valid and e.weight>1e-6]; total=sum(w for _,w in vals)
        if total<=1e-8: continue
        for name,w in vals: (dst.vertex_groups.get(name) or dst.vertex_groups.new(name=name)).add([v.index],w/total,'REPLACE')
        assigned+=1; dists.append(float(dist))
    if not any(m.type=='ARMATURE' and m.object==arm for m in dst.modifiers):
        md=dst.modifiers.new('Bodiez Mixamo Armature','ARMATURE'); md.object=arm
    return {'mesh':dst.name,'performed':True,'method':'nearest_reference_vertex','assigned_vertices':assigned,'total_vertices':len(dst.data.vertices),'coverage':round(assigned/max(1,len(dst.data.vertices)),5),'mean_reference_distance':round(sum(dists)/len(dists),6) if dists else None,'note':'Transferência de pesos não é retargeting de animação.'}

def influenced(m,bone):
    g=m.vertex_groups.get(bone)
    if not g:return []
    out=[]
    for v in m.data.vertices:
        try:
            if g.weight(v.index)>.001: out.append(v.index)
        except RuntimeError: pass
        if len(out)>=600: break
    return out

def evalpos(m,ids):
    ev=m.evaluated_get(bpy.context.evaluated_depsgraph_get()); me=ev.to_mesh()
    try:return {i:ev.matrix_world@me.vertices[i].co for i in ids if i<len(me.vertices)}
    finally:ev.to_mesh_clear()

def validate_joint(arm,meshes,bone,height):
    pb=arm.pose.bones.get(bone)
    if not pb:return {'bone':bone,'passed':False,'reason':'Osso não encontrado.'}
    samples=[]
    for m in meshes:
        ids=influenced(m,bone)
        if ids:samples.append((m,ids,evalpos(m,ids)))
    if not samples:return {'bone':bone,'passed':False,'reason':'Sem vértices influenciados.'}
    old=pb.matrix_basis.copy(); pb.rotation_mode='XYZ'; pb.rotation_euler[0]+=math.radians(22); bpy.context.view_layer.update(); moves=[]
    for m,ids,before in samples:
        after=evalpos(m,ids); moves.extend((after[i]-before[i]).length for i in before if i in after)
    pb.matrix_basis=old; bpy.context.view_layer.update(); avg=sum(moves)/len(moves) if moves else 0; passed=avg>max(height*0.0005,1e-5)
    return {'bone':bone,'passed':passed,'test_pose_degrees':22.0,'average_displacement':round(avg,7),'reason':None if passed else 'Deslocamento insuficiente.'}

def validate_joints(arm,meshes,matches):
    try:h=bounds(meshes)[1].z-bounds(meshes)[0].z
    except Exception:h=1
    regions={}; ok=True
    for region,keys in JOINTS.items():
        checks=[]
        for k in keys:
            if k in matches:
                check=validate_joint(arm,meshes,matches[k],h); check['semantic']=k; checks.append(check)
            else: checks.append({'bone':None,'semantic':k,'passed':False,'reason':'Osso semântico não identificado.'})
        passed=all(c['passed'] for c in checks); regions[region]={'passed':passed,'checks':checks}; ok=ok and passed
    return {'all_passed':ok,'regions':regions}

def export_glb(path,objs):
    path.parent.mkdir(parents=True,exist_ok=True); bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        try:o.select_set(True)
        except RuntimeError:pass
    bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,export_yup=True,export_skins=True,export_morph=True,export_animations=True)

def main():
    a=args(); source=Path(a.source).resolve(); base=Path(a.base).resolve() if a.base else None
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False); source_objs=import_model(source)
    rigs=[o for o in source_objs if o.type=='ARMATURE']
    if not rigs: raise RuntimeError('Nenhum armature encontrado.')
    ranked=sorted(((rig_info(r)['core_matches'],len(r.data.bones),r,rig_info(r)) for r in rigs),reverse=True,key=lambda x:(x[0],x[1])); arm,info=ranked[0][2],ranked[0][3]
    arm.data.pose_position='REST'; source_mesh=[m for m in source_objs if m.type=='MESH' and mesh_rig(m)==arm]; blockers=[]; warnings=[]
    if a.mode=='existing_bound':
        cov=[coverage(m,arm) for m in source_mesh]
        if not source_mesh:blockers.append('Nenhuma malha vinculada ao armature foi encontrada.')
        if any(c['coverage']<.9 for c in cov):blockers.append('Há malhas com menos de 90% dos vértices ponderados.')
        arm.data.pose_position='POSE'; joints=validate_joints(arm,source_mesh,info['semantic_matches']) if source_mesh else {'all_passed':False,'regions':{}}
        if not joints['all_passed']:blockers.append('As poses de ombros, cotovelos, quadris e joelhos precisam de revisão.')
        shapes=sum(max(0,len(m.data.shape_keys.key_blocks)-1) for m in source_mesh if m.data.shape_keys)
        report={'mode':'existing_bound','ready_for_body_customization':not blockers,'target_rig':info,'base_inspection':None,'alignment':{'performed':False,'reference_pose':'target_armature_rest_pose'},'binding':{'already_bound':True,'weight_transfer_performed':False,'weight_transfer_is_retargeting':False,'meshes':cov},'preservation':{'topology_preserved':True,'shape_keys_preserved':shapes,'destructive_modifiers_applied':False},'joint_validation':joints,'blockers':blockers,'warnings':warnings,'limitations':['Teste automático não substitui revisão artística dos pesos.','Nenhum retargeting é executado nesta etapa.']}; exports=[arm,*source_mesh]
    else:
        if not base or not base.is_file():raise RuntimeError('Base corporal não encontrada.')
        base_objs=import_base(base); base_mesh=[o for o in base_objs if o.type=='MESH']; before=inspect(base_objs)
        weighted=[m for m in source_mesh if coverage(m,arm)['coverage']>=.5]
        if not base_mesh:blockers.append('A base fornecida não contém malha.')
        if not weighted:blockers.append('O personagem Mixamo não possui malha de referência com pesos suficientes; um esqueleto sozinho não basta.')
        conflicts=[(m.name,mesh_rig(m).name) for m in base_mesh if mesh_rig(m) and mesh_rig(m)!=arm]
        if conflicts:blockers.append('A base já possui outro armature; a troca automática foi bloqueada para preservar morphs/drivers.')
        root=None; alignment={'performed':False,'reference_pose':'target_armature_rest_pose'}
        if base_mesh and (weighted or source_mesh):root,alignment=align(base_objs,weighted or source_mesh,a)
        transfers=[]
        if weighted and base_mesh and not conflicts:
            src=max(weighted,key=lambda m:len(m.data.vertices)); transfers=[transfer(src,m,arm) for m in base_mesh]
            if any(t.get('coverage',0)<.95 for t in transfers):warnings.append('Cobertura de transferência abaixo de 95%; revise os pesos.')
        else:transfers=[{'performed':False,'reason':'Transferência bloqueada ou sem referência ponderada.'}]
        arm.data.pose_position='POSE'; joints=validate_joints(arm,base_mesh,info['semantic_matches']) if any(t.get('performed') for t in transfers) else {'all_passed':False,'regions':{}}
        if any(t.get('performed') for t in transfers) and not joints['all_passed']:blockers.append('As poses diagnósticas indicam pesos que precisam de revisão.')
        after=inspect(base_objs)
        if before['shape_key_count']!=after['shape_key_count']:blockers.append('A contagem de shape keys mudou; resultado bloqueado.')
        if before['driver_count']:warnings.append('Drivers detectados foram preservados quando possível e não reinterpretados.')
        ready=not blockers and bool(base_mesh) and joints['all_passed']
        report={'mode':'adapt_base','ready_for_body_customization':ready,'target_rig':info,'base_inspection':{'before':before,'after':after,'conflicting_armatures':[{'mesh':m,'armature':r} for m,r in conflicts]},'alignment':alignment,'binding':{'already_bound':False,'weight_transfer_performed':any(t.get('performed') for t in transfers),'weight_transfer_is_retargeting':False,'method':'nearest_reference_vertex','transfers':transfers},'preservation':{'topology_preserved':True,'shape_keys_before':before['shape_key_count'],'shape_keys_after':after['shape_key_count'],'drivers_before':before['driver_count'],'drivers_after':after['driver_count'],'destructive_modifiers_applied':False},'joint_validation':joints,'blockers':blockers,'warnings':warnings,'limitations':['Alinhamento automático é global; A/T-pose e diferenças anatômicas podem exigir ajuste manual.','Transferência por proximidade é preparação inicial e não substitui pintura profissional de pesos.','Transferência de pesos não é retargeting de animação.','Rigs proprietários e controles não são convertidos automaticamente.']}; exports=[arm,*base_mesh]+([root] if root else [])
        for m in source_mesh:m.hide_render=True;m.hide_viewport=True
    report['safety']={'original_files_modified':False,'arbitrary_script_received_from_ui':False,'shell_commands_received_from_ui':False}
    rp=Path(a.report); rp.parent.mkdir(parents=True,exist_ok=True); rp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    bp=Path(a.blend); bp.parent.mkdir(parents=True,exist_ok=True); bpy.ops.wm.save_as_mainfile(filepath=str(bp)); export_glb(Path(a.preview),exports)
    print(RESULT_PREFIX+json.dumps({'ok':True,'ready':report['ready_for_body_customization'],'blockers':len(blockers),'warnings':len(warnings)}),flush=True)

if __name__=='__main__':
    try:main()
    except Exception:traceback.print_exc();raise
