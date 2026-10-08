"""Offline terrain queries over exported native heightfields; never invent a floor.

This covers landscape triangles only. Static meshes and capsule sweeps remain
separate requirements; a point sample alone does not prove capsule clearance.
"""
import math
import struct
from dataclasses import dataclass


@dataclass
class Heightfield:
    rows: int
    cols: int
    origin: tuple
    scale: tuple
    minimum: float
    quantization: float
    heights: bytes
    materials: bytes

    def __post_init__(self):
        if not 2 <= self.rows <= 4096 or not 2 <= self.cols <= 4096:
            raise ValueError('bounded heightfield dimensions required')
        if len(self.heights) != self.rows*self.cols*2:
            raise ValueError('height sample count mismatch')
        if len(self.materials) != (self.rows-1)*(self.cols-1):
            raise ValueError('collision cell count mismatch')
        if not all(math.isfinite(v) for v in (*self.origin, *self.scale,
                                              self.minimum, self.quantization)):
            raise ValueError('finite terrain transform required')
        if len(self.origin) != 3 or len(self.scale) != 3 or min(self.scale) <= 0 or self.quantization < 0:
            raise ValueError('positive axis-aligned terrain scale required')

    def vertex(self, x, y):
        sample = struct.unpack_from('<H', self.heights, 2*(y*self.cols+x))[0]
        return self.origin[2]+(self.minimum+sample*self.quantization)*self.scale[2]

    def ground(self, x, y):
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError('finite query required')
        gx=(x-self.origin[0])/self.scale[0]
        gy=(y-self.origin[1])/self.scale[1]
        # Half-open bounds prevent reading a neighbouring or missing tile.
        if not 0 <= gx < self.cols-1 or not 0 <= gy < self.rows-1:
            return None
        ix,iy=math.floor(gx),math.floor(gy)
        if self.materials[iy*(self.cols-1)+ix] == 255:
            return None
        fx,fy=gx-ix,gy-iy
        h00,h10,h01,h11=(self.vertex(a,b) for a,b in
            ((ix,iy),(ix+1,iy),(ix,iy+1),(ix+1,iy+1)))
        # Native triangle diagonal: (00,10,11), then (00,11,01).
        if fx >= fy:
            dx,dy=h10-h00,h11-h10
            z=h00+fx*dx+fy*dy
        else:
            dx,dy=h11-h01,h01-h00
            z=h00+fx*dx+fy*dy
        nx,ny=-dx/self.scale[0],-dy/self.scale[1]
        norm=math.sqrt(nx*nx+ny*ny+1)
        return {'height':z,'normal':[nx/norm,ny/norm,1/norm],
                'cell':[ix,iy], 'material':self.materials[iy*(self.cols-1)+ix]}

    def triangles(self, minimum, maximum):
        """Native solid triangles in a swept capsule's XY broad phase."""
        lo=[max(0,math.floor((minimum[i]-self.origin[i])/self.scale[i])) for i in range(2)]
        hi=[min((self.cols,self.rows)[i]-2,math.floor((maximum[i]-self.origin[i])/self.scale[i])) for i in range(2)]
        for y in range(lo[1],hi[1]+1):
            for x in range(lo[0],hi[0]+1):
                if self.materials[y*(self.cols-1)+x]==255:continue
                points=[(self.origin[0]+a*self.scale[0],self.origin[1]+b*self.scale[1],self.vertex(a,b))
                        for a,b in ((x,y),(x+1,y),(x,y+1),(x+1,y+1))]
                yield (points[0],points[1],points[3])
                yield (points[0],points[3],points[2])


def highest_ground(tiles, x, y):
    hits=[hit for tile in tiles if (hit:=tile.ground(x,y)) is not None]
    return max(hits,key=lambda hit:hit['height']) if hits else None
