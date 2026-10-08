"""Small read-only, seed/lifetime/weak-bound physics snapshot; no object scan/calls/input."""
import argparse,hashlib,json,math,struct,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from inspect_character_stats import hash_entry
from dump_runtime_reflection import Reader,pointer
from protocol_proof import EXPECTED_EXE,client_proof

def inspect(pid,creation,seed):
    data=json.loads(seed.read_bytes());before=client_proof(pid)
    for k in ['pid','exe','sha256','process_created_filetime']:assert before[k]==data['client_proof'][k]
    assert before['pid']==pid and before['process_created_filetime']==creation
    candidates=[c for c in data['controllers'] if c.get('acknowledged_pawn') and c.get('pawn') and c['acknowledged_pawn']['address']==c['pawn']['address']]
    assert len(candidates)==1
    c=candidates[0];controller=int(c['address'],16);pawn=int(c['pawn']['address'],16)
    reader=Reader(pid,EXPECTED_EXE,budget=4*1024*1024)
    try:
        p=MovementProbe(reader)
        def identity(address,expected=None,positive=True):
            ident=p.identity(address,expected);i=ident['object_index'];assert 0<=i<p.reflection.count
            chunk=reader.unpack(p.reflection.chunks+i//65536*8,'<Q')[0]
            actual,flags,cluster,serial=reader.unpack(chunk+i%65536*24,'<Qiii')
            assert actual==address and not flags&0x10200000 and (not positive or serial>0)
            return dict(ident,serial=serial,flags=hex(flags))
        ids=[identity(controller,'PlayerController'),identity(pawn,'Character')]
        for live,stored in zip(ids,[c,c['pawn']]):
            assert live['object_index']==stored['object_index'] and live['serial']==stored['serial']
        possession=p.controller(controller);assert possession['acknowledges_same_pawn'] and possession['pawn_points_back_to_controller']
        assert possession['pawn']['address']==hex(pawn)
        owner=p.fields(pawn,['CharacterMovement','RootComponent','Mesh','StatsComponent'])
        movement=int(owner['CharacterMovement']['value']['address'],16);ids.append(identity(movement,'CharacterMovementComponent'))
        mt=reader.unpack(movement,'<Q')[0];pt=reader.unpack(pawn,'<Q')[0]
        bindings=[]
        assert reader.unpack(movement+0x1300,'<Q')[0]==pawn
        for table,slot,target in [(mt,0x560,0x5ea4b00),(mt,0x770,0x5ea1480),(mt,0x808,0x5ea51c0),(mt,0x810,0x5ea51d0),(mt,0x888,0x3ddc2f0),(mt,0x898,0x3dc5320),(mt,0xd60,0x5ea6560),(mt,0xcd8,0x5ea2150),(pt,0xcf0,0x6b411a0),(pt,0xcf8,0x6b4d430)]:
            actual=reader.unpack(table+slot,'<Q')[0]-reader.base;assert actual==target
            bindings.append(dict(table_rva=hex(table-reader.base),slot=hex(slot),target_rva=hex(target)))
        pawn_fields=p.fields(pawn,['bPressedJump','JumpKeyHoldTime','JumpForceTimeRemaining','JumpMaxHoldTime','JumpMaxCount','JumpCurrentCount','JumpCurrentCountPreJump','bWasJumping'])
        movement_fields=p.fields(movement,['UpdatedComponent','UpdatedPrimitive','MovementMode','Velocity','GravityScale','GravityDirection','JumpZVelocity','AirControl','AirControlBoostMultiplier','AirControlBoostVelocityThreshold','FallingLateralFriction','BrakingDecelerationFalling','BrakingFriction','BrakingFrictionFactor','bUseSeparateBrakingFriction','bApplyGravityWhileJumping','bDontFallBelowJumpZVelocityDuringJump','MaxSimulationTimeStep','MaxSimulationIterations','MaxJumpApexAttemptsPerSimulation','bForceMaxAccel','MaxWalkSpeed','MaxSprintSpeed','JumpHorizontalSpeedBoost','JumpStepUpHeightScale','FallingStepUpHeightScale'])
        movement_fields.update(p.fields(movement,['MaxAcceleration','bUseAccelerationStat','AccelerationStat','MaxStepHeight','WalkableFloorZ','WalkableFloorAngle','bMaintainHorizontalGroundVelocity','bUseFlatBaseForFloorChecks','PerchRadiusThreshold','PerchAdditionalHeight','MaxDepenetrationWithGeometry','MaxDepenetrationWithGeometryAsProxy','MaxDepenetrationWithPawn','MaxDepenetrationWithPawnAsProxy']))
        for name,offset,size in [('MaxAcceleration',0x2dc,4),('bUseAccelerationStat',0x1190,1),('AccelerationStat',0x1198,56)]:p.property(movement,name,offset,size)
        air_leads=dict(current_owner1300_agrees=True,selector_owner_byte1321=reader.unpack(pawn+0x1321,'<B')[0],
            dojump_condition_byte1015=reader.unpack(movement+0x1015,'<B')[0],dojump_horizontal_condition_byte101c=reader.unpack(movement+0x101c,'<B')[0],
            step_leads_raw1014_1020=reader.read(movement+0x1014,12).hex(),lateral_accel_override_byte_f50=reader.unpack(movement+0xf50,'<B')[0],
            apex_enable_runtime_global_d26ee98=reader.unpack(reader.base+0xd26ee98,'<i')[0],
            limits=['Native getter-use leads and raw bytes, not newly reflected property labels.','Stat-enabled effective acceleration requires configured definition/native stat cache evaluation; raw MaxAcceleration is not sufficient.'])
        vpget=reader.unpack(mt+0x588,'<Q')[0];volume_getter=dict(slot='0x588',target_rva=hex(vpget-reader.base),prefix128=reader.read(vpget,128).hex(),boundary='Discovery prefix only; not complete function')
        assert reader.read(reader.base+0x43f8f87,7).hex()=='488b0582cf4509'
        pc=reader.unpack(reader.base+0xd855f10,'<Q')[0];assert pointer(pc)
        pci=identity(pc,'Class',False);assert pci['name']=='PhysicsSettings'
        pd=reader.unpack(pc+0x150,'<Q')[0];pdi=identity(pd,'PhysicsSettings',False);assert pdi['name']=='Default__PhysicsSettings'
        p.property(pd,'DefaultGravityZ',0x58,4)
        physics_defaults=dict(class_identity=pci,cdo_identity=pdi,fields=p.fields(pd,['DefaultGravityZ']),class_getter_rva='0x43f8f80',class_global_rva='0xd855f10')
        root=int(owner['RootComponent']['value']['address'],16);ids.append(identity(root,'SceneComponent'))
        shape=p.fields(root,['CapsuleHalfHeight','CapsuleRadius','RelativeScale3D','bGenerateOverlapEvents','bUseAttachParentBound'])
        volume=None;volume_source=None;prop=p.properties_for(root).get('PhysicsVolume')
        if prop and prop['type']=='WeakObjectProperty' and prop['element_size']==8:
            index,serial=reader.unpack(root+prop['offset_in_object'],'<ii')
            if serial>0:
                assert 0<=index<p.reflection.count
                chunk=reader.unpack(p.reflection.chunks+index//65536*8,'<Q')[0]
                address,flags,cluster,actual=reader.unpack(chunk+index%65536*24,'<Qiii');assert actual==serial and not flags&0x10200000
                volume=identity(address,'PhysicsVolume');ids.append(volume);volume_source='RootComponent.PhysicsVolume positive weak identity'
        level=int(ids[1]['outer_address'],16);ids.append(identity(level,'Level'))
        world=int(p.fields(level,['OwningWorld'])['OwningWorld']['value']['address'],16);ids.append(identity(world,'World'))
        wf=p.fields(world,['DefaultPhysicsVolume','PersistentLevel','GameState']);world_settings=None
        if not volume and wf['DefaultPhysicsVolume'].get('value'):
            volume=identity(int(wf['DefaultPhysicsVolume']['value']['address'],16),'PhysicsVolume');ids.append(volume);volume_source='World.DefaultPhysicsVolume fallback (root weak absent)'
        if wf['PersistentLevel'].get('value'):
            persistent=int(wf['PersistentLevel']['value']['address'],16)
            ws=p.fields(persistent,['WorldSettings'])['WorldSettings'].get('value')
            if ws:
                wsa=int(ws['address'],16);wvt=reader.unpack(wsa,'<Q')[0];gt=reader.unpack(wvt+0x840,'<Q')[0]
                world_settings=dict(identity=identity(wsa,'WorldSettings'),fields=p.fields(wsa,['WorldGravityZ','GlobalGravityZ','bGlobalGravitySet']),get_gravity_slot840_rva=hex(gt-reader.base),get_gravity_prefix128=reader.read(gt,128).hex(),prefix_boundary='Discovery prefix only; not a complete function claim')
                ids.append(world_settings['identity'])
        volume_report=None
        if volume:
            address=int(volume['address'],16);vt=reader.unpack(address,'<Q')[0]
            volume_report=dict(identity=volume,source=volume_source,fields=p.fields(address,['TerminalVelocity','FluidFriction','bWaterVolume']),get_gravity_slot840_rva=hex(reader.unpack(vt+0x840,'<Q')[0]-reader.base))
        animation=None
        if owner['Mesh'].get('value'):
            mesh=int(owner['Mesh']['value']['address'],16);ids.append(identity(mesh,'SkeletalMeshComponent'))
            anim=p.fields(mesh,['AnimScriptInstance'])['AnimScriptInstance'].get('value')
            if anim:
                addr=int(anim['address'],16);ai=identity(addr,'AnimInstance');ids.append(ai)
                ptr,n,cap=reader.unpack(addr+0xb8,'<Qii');assert 0<=n<=cap<=512 and (not n or pointer(ptr))
                animation=dict(identity=ai,native_modifier_array_pointer=hex(ptr),count=n,capacity=cap,
                    meaning='6B411A0 arrayB8/countC0; empty establishes no additional active array entries; nonempty requires curve/predicate evaluation')
        config=None
        index,serial=reader.unpack(reader.base+0xd932ba0,'<ii');assert 0<=index<p.reflection.count and serial>0
        chunk=reader.unpack(p.reflection.chunks+index//65536*8,'<Q')[0]
        manager,flags,cluster,actual=reader.unpack(chunk+index%65536*24,'<Qiii');assert actual==serial and not flags&0x10200000
        ids.append(identity(manager,'DesignDataManagerBase'))
        te=hash_entry(reader,manager+0x1f0,0xb0,0x6a9c0102f8f941c0);assert te
        ce=hash_entry(reader,te+8,24,0x636a8ad25678);assert ce
        record=reader.unpack(ce+8,'<Q')[0];assert pointer(record) and reader.unpack(record+8,'<Q')[0]==0x636a8ad25678
        cached,guid,type_id=reader.unpack(record+0x1530,'<QQQ');assert pointer(cached) and reader.unpack(cached+8,'<Q')[0]==guid
        ni,nn=reader.unpack(cached+0x18,'<II')
        config=dict(record_id='0x636a8ad25678',record_address=hex(record),gravity_id=hex(guid),gravity_type=hex(type_id),cached_record_address=hex(cached),cached_name=p.reflection.names.get(ni,nn),cached_type_byte=reader.unpack(cached+0x79,'<B')[0],stat_entries=[])
        stats=int(owner['StatsComponent']['value']['address'],16);ids.append(identity(stats))
        for name,stride in [('StatsInt32',56),('StatsFloatArray',40)]:
            prop=p.properties_for(stats)[name];entry=hash_entry(reader,stats+prop['offset_in_object'],stride,guid)
            if entry:
                raw=reader.read(entry,stride);row=dict(map=name,address=hex(entry),raw=raw.hex())
                if name=='StatsInt32':row.update(packed_values=list(struct.unpack_from('<4i',raw,8)),float_values=list(struct.unpack_from('<4f',raw,8)))
                else:
                    ptr,n,cap=struct.unpack_from('<Qii',raw,8);assert 0<=n<=cap<=256 and (not n or pointer(ptr))
                    row.update(count=n,capacity=cap,values=[list(reader.unpack(ptr+j*112+16,'<fff')) for j in range(n)])
                config['stat_entries'].append(row)
        slow_fall=p.fields(stats,['bIsSlowFalling']);slow_leaf=reader.read(reader.base+0x612dae0,8);assert slow_leaf.hex()=='0fb68144080000c3'
        slow_fall['native_leaf']=dict(rva='0x612dae0',bytes=slow_leaf.hex(),meaning='MOVZX Stats+844 and RET; exact bIsSlowFalling reflected byte')
        for ident in ids:assert identity(int(ident['address'],16))['serial']==ident['serial']
        again=p.controller(controller);assert again['acknowledges_same_pawn'] and again['pawn_points_back_to_controller'] and again['pawn']['address']==hex(pawn)
        after=client_proof(pid)
        for k in ['pid','exe','sha256','process_created_filetime']:assert before[k]==after[k]
        return dict(client_proof=after,seed=dict(path=str(seed),sha256=hashlib.sha256(seed.read_bytes()).hexdigest()),identities=ids,possession=possession,bindings=bindings,pawn=pawn_fields,movement=movement_fields,air_native_leads=air_leads,shape=shape,world_settings=world_settings,physics_volume=volume_report,physics_volume_getter=volume_getter,physics_defaults=physics_defaults,animation=animation,gravity_configuration=config,slow_fall_fields=slow_fall,bytes_read=reader.bytes_read,
            access='VM_READ/query only; no object scan/calls/input/writes/packets',limits=['Sampled idle values and static slot bindings; actual jump/fall/apex/landing trial still required.', 'Raw cached stat values are not a native function invocation; nonempty animation modifiers or stat modifiers require further evaluation.', 'Volume selection/WorldSettings fields alone are not proof of every effective gravity getter path.'])
    finally:reader.close()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pid',required=True,type=int);ap.add_argument('--creation',required=True,type=int);ap.add_argument('--seed',type=Path,default=R.parent/'CPP/data/client-inspection.json');args=ap.parse_args()
    report=inspect(args.pid,args.creation,args.seed)
    dest=R/f'proofs/jump-gravity-live-{args.pid}-{args.creation}-{time.time_ns()}.json';dest.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(path=str(dest),bytes_read=report['bytes_read'],pawn={k:v.get('value',v['status']) for k,v in report['pawn'].items()},movement={k:v.get('value',v['status']) for k,v in report['movement'].items()},configuration=report['gravity_configuration'],animation=report['animation']),indent=2))
