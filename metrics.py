from sqlite3 import OperationalError
import psycopg2
import numpy as np
from PIL import Image
from io import BytesIO
import base64
from skimage.measure import label, regionprops
from skimage.transform import resize
import json

def bytesToImage(imageStr):
    _, data = imageStr.split(',', 1)
    binary_data = base64.b64decode(data)

    image = Image.open(BytesIO(binary_data))
    image = np.asarray(image)
    return image

# def extract_color_hex_triplets(node, result):
#     if "color_hex_triplet" in node:
#         result.append(node["color_hex_triplet"])
#     if "children" in node:
#         for child in node["children"]:
#             extract_color_hex_triplets(child, result)
            
def get_metrics(currentsection,biosample,annotated_mask,coords,ontologyTree):
    try:
        # try:
        #     color_hex = json.load(ontologyTree.decode())
        #     color_hex_triplets = []
        #     for item in color_hex["msg"]:
        #         extract_color_hex_triplets(item, color_hex_triplets)
        # except Exception as e:
        #     print(e,'**************')
            
        coords_array = np.array(coords)
        tileregion = coords_array.squeeze()

        left = tileregion[:,0].min()
        top = -tileregion[:,1].max()
        right = tileregion[:,0].max()
        bottom = -tileregion[:,1].min()
        pt1 = left,top  #x,y
        pt2 = right,bottom #x,y
        conn = psycopg2.connect(dbname=biosample,
                                user='myuser',
                                password='mypass',
                                host='ap3.humanbrain.in',
                                port=5432)
        sec_points,_ = get_points(conn,(pt1,pt2),currentsection,slice(currentsection,currentsection))
        conn.close()
        outmask = np.zeros((bottom-top,right-left),np.uint8)
        pts_list=[]
        
        if currentsection in sec_points:
            pts_list = sec_points[currentsection]
        
        print(len(pts_list))
            
        for ptt in pts_list:
            localpt = int(ptt[1]-top), int(ptt[0]-left)
            outmask[localpt[0]:localpt[0]+2,localpt[1]:localpt[1]+2]=255
            
        # data = Image.fromarray(outmask,'RGBA')
        # byte_io = BytesIO()
        # data.save(byte_io, 'PNG')
        # encoded = base64.b64encode(byte_io.getvalue())
        
        annotated_img = bytesToImage(annotated_mask)
        print(annotated_img.shape)
        annotated_img = resize(annotated_img.max(axis=2)>0,outmask.shape,order=0)
        props = regionprops(label(annotated_img))
        Ndet = len(props)
        Ngt = len(pts_list)
        vals = np.zeros((Ndet,1))
        for ii,x in enumerate(props):
            cr,cc = x.centroid
            vals[ii] = outmask[int(round(cr,0)),int(round(cc,0))]
        TPval = (vals==255).sum()
        FPval = (vals==0).sum()
        FNval = Ngt - TPval
        
        print(TPval,FPval,FNval,'************')
        tpr =  "{:.3f}".format( TPval / Ngt)
        fdr =  "{:.3f}".format(FPval/(FPval+TPval))
        f1 =  "{:.3f}".format(2*TPval/(2*TPval+FPval+FNval))

            
    except Exception as e:
        return e
    
    metrics_data =  {
                        "counts": {
                            "ngt": int(Ngt),
                            "ntp": int(TPval),
                            "nfp": int(FPval),
                            "nfn": int(FNval),
                        },
                        "pc": {
                            "tpr": float(tpr),
                            "fdr": float(fdr),
                            "f1": float(f1),
                            "actual_effort_needed": 0
                        }
                    }
    
    return metrics_data


def pg_linestring(pt1,pt2):
    return f'LINESTRING({pt1[0]} {pt1[1]},{pt2[0]} {pt2[1]})'

def get_points(conn,pts,sec,slc):
    with conn.cursor() as curs:
        ls = pg_linestring(pts[0],pts[1])
        query = f"""
                SELECT name
                FROM summary
                WHERE inputarg LIKE '%SE_{sec}_lossless.jp2%'
                ORDER BY name DESC
                LIMIT 1;
            """
        curs.execute(query)
        tablename = curs.fetchone()[0]
        query1 = f"select section,centroid from {tablename} where (section between {slc.start} and {slc.stop}) and ST_Within(centroid::geometry,ST_Envelope('{ls}'))"
        print(query1)
        curs.execute(query1)

        section_points = {}
        cloud_points = []

        for res in curs:
            sec = res[0]
            cen = [float(v) for v in res[1][1:-1].split(',')]
            if sec not in section_points:
                section_points[sec]=[]
            section_points[sec].append([cen[0],cen[1]])
            cloud_points.append([cen[0],cen[1],float(sec)])
            
    return section_points, cloud_points
    
    
def handleregionInput(currentsection, geojson,biosample):
    try:
        conn = psycopg2.connect(
            dbname=biosample,
            user='myuser',
            password='mypass',
            host='ap3.humanbrain.in',
            port=5432
        )
        formated_geojson = f"ST_MakeValid(ST_GeomFromGeoJSON('{geojson}'))"
        cursor = conn.cursor()
        query = f"""
            SELECT inputarg
            FROM summary
            WHERE inputarg='{currentsection}'
            ORDER BY name DESC
            LIMIT 1;
        """
        # WHERE inputarg LIKE '%SE_{currentsection}_lossless.jp2%'
        
        cursor.execute(query)
        result = cursor.fetchone()

        if result:
            inputarg_result = result[0]
            print(f"Inputarg {inputarg_result} found!")
            query = f"""
                SELECT name
                FROM summary
                WHERE inputarg='{currentsection}'
                ORDER BY name DESC
                LIMIT 1;
            """
            # WHERE inputarg LIKE '%SE_{currentsection}_lossless.jp2%'
            cursor.execute(query)
            table_name = cursor.fetchone()[0]
            centroid_count_query = f"""
                SELECT count(*) AS centroid_count
                FROM {table_name}
                WHERE ST_Within(
                    ST_SetSRID(ST_MakePoint(centroid[0], -centroid[1]), 4326), 
                    ST_SetSRID({formated_geojson}, 4326));
                """
            print("centroid_count_query:",centroid_count_query)
            cursor.execute(centroid_count_query)
            centroid_count_result = cursor.fetchone()[0]

            total_centroid_count_query = f"""
                SELECT COUNT(*) AS total_centroid_count
                FROM {table_name};
            """
            
            print("total_centroid_count_query",total_centroid_count_query)
            
            cursor.execute(total_centroid_count_query)
            total_centroid_count_result = cursor.fetchone()[0]
            
            area_of_geojson = f"""
                SELECT ST_Area(
                    ST_Union(ST_SetSRID({formated_geojson}, 4326)));"""
            
            
            print("area_of_geojson",area_of_geojson)
            
            cursor.execute(area_of_geojson)
            area_of_geojson_result = cursor.fetchone()[0]
            
            area = round(area_of_geojson_result * 0.25 * (10 ** -6),2)
            # unit = "μm²"
            unit = "mm²"
            formatted_area = f"{area} {unit}"
    
            perimeter_of_geojson = f"""
                SELECT ST_Perimeter(
                    {formated_geojson}) AS perimeter;"""  
            
            
            print("perimeter_of_geojson",perimeter_of_geojson)
            cursor.execute(perimeter_of_geojson)
            perimeter_of_geojson_result = cursor.fetchone()[0]
            
            perimeter = round(perimeter_of_geojson_result * 0.5 * (10**-3),2)
            unit = "mm"
            formatted_perimeter = f"{perimeter} {unit}"
            
            Cell_Density = round(centroid_count_result / area , 3)
            # unit ="%"
            formatted_Cell_Density = f"{Cell_Density} "


            cursor.close()
            conn.close()
            finalData =  {
                'Area':formatted_area,
                'Perimeter':formatted_perimeter,
                "centroid_count": centroid_count_result,
                # "centroid_count": 25634,
                "total_centroid_count": int(total_centroid_count_result),
                'volume':0000,
                'surface_area':0000,
                'cell_density':formatted_Cell_Density,
                'volume_cell_density':0000
            }
            print("finalData",finalData)
            return finalData
        else:
            print(f"Inputarg {currentsection} not found in the database.")
            area_of_geojson = f"""
                SELECT ST_Area(
                    ST_Union(ST_SetSRID({formated_geojson}, 4326)));"""
            
            
            print("area_of_geojson",area_of_geojson)
            
            cursor.execute(area_of_geojson)
            area_of_geojson_result = cursor.fetchone()[0]
            
            area = round(area_of_geojson_result * 0.25 * (10 ** -6),2)
            # unit = "μm²"
            unit = "mm²"
            formatted_area = f"{area} {unit}"
    
            
            
            # area_in_micron = f"""
            #     SELECT ST_Area(
            #         ST_Union(ST_GeomFromGeoJSON(
            #             '{geojson}'))) * POWER(10, 12) 
            #             AS total_area_in_microns 
            #     FROM {table_name};"""
            
            perimeter_of_geojson = f"""
                SELECT ST_Perimeter(
                    {formated_geojson}) AS perimeter;"""  
            
            
            print("perimeter_of_geojson",perimeter_of_geojson)
            cursor.execute(perimeter_of_geojson)
            perimeter_of_geojson_result = cursor.fetchone()[0]
            
            perimeter = round(perimeter_of_geojson_result * 0.5 * (10**-3),2)
            unit = "mm"
            formatted_perimeter = f"{perimeter} {unit}"
            cursor.close()
            conn.close()
            finalData =  {
                'Area':formatted_area,
                'Perimeter':formatted_perimeter,
                "centroid_count": "-----",
                # "centroid_count": 25634,
                "total_centroid_count": "-----",
                'volume':'-----',
                'surface_area':'-----',
                'cell_density':'-----',
                'volume_cell_density':'-----'
            }
            print("finalData",finalData)
            return finalData
        
    except OperationalError as e:
            print("database not found:",biosample)
            formated_geojson = f"ST_MakeValid(ST_GeomFromGeoJSON('{geojson}'))"
            
            area_of_geojson = f"""
                SELECT ST_Area(
                    ST_Union(ST_SetSRID({formated_geojson}, 4326))
                );
            """
            
            perimeter_of_geojson = f"""
                SELECT ST_Perimeter(
                    {formated_geojson}
                ) AS perimeter;
            """
            
            conn = psycopg2.connect(
                dbname=220,  # Use a default database or specify one that exists
                user='myuser',
                password='mypass',
                host='ap3.humanbrain.in',
                port=5432
            )
            cursor = conn.cursor()
            
            cursor.execute(area_of_geojson)
            area_of_geojson_result1 = cursor.fetchone()[0]
            area1 = round(area_of_geojson_result1 * 0.25 * (10 ** -6),2)
            # unit = "μm²"
            unit = "mm²"
            formatted_area1 = f"{area1} {unit}"
            
            cursor.execute(perimeter_of_geojson)
            perimeter_of_geojson_result1 = cursor.fetchone()[0]
            perimeter1 = round(perimeter_of_geojson_result1 * 0.5 * (10**-3),2)
            unit = "mm"
            formatted_perimeter1 = f"{perimeter1} {unit}"
            
            cursor.close()
            conn.close()
            
            finalData = {
                'Area': formatted_area1,
                'Perimeter': formatted_perimeter1,
                "centroid_count": '-----',
                "total_centroid_count": '-----',
                'volume':'-----',
                'surface_area':'-----',
                'cell_density':'-----',
                'volume_cell_density':'-----'
            }
            
            print("finalData",finalData)
            
            return finalData 
     

    except Exception as e:
        return {"error": str(e)}
    
    
