#include "ashes/backend.hpp"
#include <cstring>
#include <set>
namespace ashes {
namespace {
uint64_t hash_entry(ProcessReader& r,uint64_t base,size_t stride,uint64_t key){
 auto slots=r.at<uint64_t>(base);int count=r.at<int32_t>(base+8),capacity=r.at<int32_t>(base+12),free_count=r.at<int32_t>(base+0x34),buckets=r.at<int32_t>(base+0x48);
 if(!count)return 0;require(slots&&free_count>=0&&free_count<=count&&count<=capacity&&capacity<=1000000&&buckets>0&&buckets<=1048576&&!(buckets&(buckets-1)),"Bounded native record hash map required");
 auto table=r.at<uint64_t>(base+0x40);if(!table)table=base+0x38;int index=r.at<int32_t>(table+4*(((key>>32)*23+key)&uint64_t(buckets-1)));std::set<int> seen;
 while(index!=-1){require(index>=0&&index<count&&seen.insert(index).second&&seen.size()<=4096,"Bounded unique native record chain required");auto entry=slots+size_t(index)*stride;if(r.at<uint64_t>(entry)==key)return entry;index=r.at<int32_t>(entry+stride-8);}return 0;
}
}
uint32_t read_resource_stat(Reflection& f,uint64_t stats,uint64_t record,int scope){
 auto& r=f.r;int index=r.at<int32_t>(r.base+0xd932ba0),serial=r.at<int32_t>(r.base+0xd932ba4);require(index>=0&&unsigned(index)<f.count&&serial>0,"Live design manager weak reference required");auto chunk=r.at<uint64_t>(f.chunks+8*(unsigned(index)/65536)),slot=chunk+size_t(unsigned(index)%65536)*24;
 require(r.at<int32_t>(slot+16)==serial&&!(r.at<uint32_t>(slot+8)&0x10200000),"Current design manager lifetime required");auto manager=r.at<uint64_t>(slot);f.identity(manager,"DesignDataManagerBase");
 auto type=hash_entry(r,manager+0x1f0,0xb0,0x4a74ae5ed850dc97ULL);require(type,"Native StatTypeDef design table required");auto entry=hash_entry(r,type+8,24,record);require(entry,"Native resource stat definition required");auto definition=r.at<uint64_t>(entry+8);
 require(definition&&r.at<uint64_t>(definition+8)==record&&r.at<uint8_t>(definition+0x79)==0&&r.at<uint8_t>(definition+0x247)==0,"Reviewed resource float type and bucket layout required");
 require(scope>=0&&r.at<uint8_t>(definition+0x246)==scope,"Reviewed resource replication scope required");
 if(record==0x5429e5e8643f0018ULL){
  auto profiles=hash_entry(r,manager+0x1f0,0xb0,0x6a9c0102f8f941c0ULL);require(profiles,"Current GameStatProfile table required");auto profile=hash_entry(r,profiles+8,24,0x636a8ad25678ULL);require(profile,"Reviewed GameStatProfile record required");auto data=r.at<uint64_t>(profile+8);
  require(data&&r.at<uint64_t>(data+8)==0x636a8ad25678ULL&&r.at<uint64_t>(data+0x1530)==definition&&r.at<uint64_t>(data+0x1538)==record&&r.at<uint64_t>(data+0x1540)==0x4a74ae5ed850dc97ULL,"Character gravity getter cached record binding changed");
 }
 f.property(stats,"StatsInt32",0x668,0x50);auto cached=hash_entry(r,stats+0x668,56,record);require(cached,"Existing native resource cache required; do not manufacture unknown stats");
 auto expected=unhex("8b0189442408f30f10442408c3");require(r.read(r.base+0x6175ec0,expected.size())==expected,"Native stat float-bit getter changed");return r.at<uint32_t>(cached+12);
}
}
