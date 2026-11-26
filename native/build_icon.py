"""Render the Meridian mark as a multi-size, RGBA Windows application icon."""
from pathlib import Path
import struct
import zlib

def png(n):
    def chunk(kind,data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data))
    rows=bytearray()
    for y in range(n):
        rows.append(0)
        for x in range(n):
            u,v=(x+.5)/n,(y+.5)/n
            edge=(max(0,.17-u,u-.83)**2+max(0,.17-v,v-.83)**2)**.5
            dark=any(a<u<b and t-.07*(u-a)/(b-a)<v<bottom-.07*(u-a)/(b-a)
                for a,b,t,bottom in [(0.23,.36,.49,.74),(.435,.565,.29,.78),(.64,.77,.37,.71)])
            rows.extend((23,54,42,255) if dark else (159,231,190,255 if edge<=.17 else 0))
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">2I5B",n,n,8,6,0,0,0))+
            chunk(b"IDAT",zlib.compress(bytes(rows),9))+chunk(b"IEND",b""))

sizes=[16,24,32,48,64,128,256]
images=[png(n) for n in sizes]
head=struct.pack("<3H",0,1,len(images))
offset=6+16*len(images)
for size,img in zip(sizes,images):
    head+=struct.pack("<4B2H2I",size%256,size%256,0,0,1,32,len(img),offset)
    offset+=len(img)
(Path(__file__).resolve().parents[1]/"app"/"meridian.ico").write_bytes(head+b"".join(images))
