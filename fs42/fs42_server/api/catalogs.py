from fastapi import APIRouter
from fs42.station_manager import StationManager
from fs42.catalog_api import CatalogAPI

router = APIRouter(prefix="/catalogs", tags=["catalogs"])

@router.get("/search_all")
async def search_all_catalogs(query: str = None):
    station_manager = StationManager()
    all_results = []
    
    for station in station_manager.stations:
        if station.get("_has_catalog", False):
            try:
                if query:
                    catalog_entries = CatalogAPI.search_entries(station, query)
                else:
                    catalog_entries = CatalogAPI.get_entries(station)
                
                if catalog_entries:
                    all_results.append({
                        "network_name": station["network_name"],
                        "catalog_entries": catalog_entries
                    })
            except Exception as e:
                all_results.append({
                    "network_name": station["network_name"],
                    "error": str(e),
                    "catalog_entries": []
                })
    
    return {"query": query, "results": all_results}

@router.get("/{network_name}")
async def get_catalog(network_name: str):
    conf = StationManager().station_by_name(network_name)
    catalog_entries = CatalogAPI.get_entries(conf)
    return {"network_name": network_name, "catalog_entries": catalog_entries}

@router.get("/search/{network_name}")
async def search_catalog(network_name: str, query: str = None):
    conf = StationManager().station_by_name(network_name)
    if query:
        catalog_entries = CatalogAPI.search_entries(conf, query)
    else:
        catalog_entries = CatalogAPI.get_entries(conf)

    return {"network_name": network_name, "query": query, "catalog_entries": catalog_entries}
