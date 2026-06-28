"""Mapping between CV class names and Vietnamese display names / crop categories."""

# Maps CV class label → Vietnamese disease name (for query enrichment)
CLASS_TO_VN: dict[str, str] = {
    "Cafe_benh_dom_rong":       "bệnh đốm rong cà phê",
    "Cafe_benh_nam_ri_sat":     "bệnh nấm rỉ sắt cà phê",
    "Cafe_benh_phan_trang":     "bệnh phấn trắng cà phê",
    "Cafe_benh_phoma":          "bệnh phoma cà phê",
    "Cafe_benh_sau_ve_bua":     "bệnh sâu vẽ bùa cà phê",
    "Cafe_khoe_manh":           "cà phê khỏe mạnh",
    "Lua_benh_dao_on_co_bong":  "bệnh đạo ôn cổ bông lúa",
    "Lua_benh_dao_on_la":       "bệnh đạo ôn lá lúa",
    "Lua_benh_dom_nau":         "bệnh đốm nâu lúa",
    "Lua_benh_sau_gai_hispa":   "bệnh sâu gai hispa lúa",
    "Lua_benh_vang_la_tungro":  "bệnh vàng lá tungro lúa",
    "Lua_khoe_manh":            "lúa khỏe mạnh",
    "Mia_benh_choi_co":         "bệnh chồi cỏ mía",
    "Mia_benh_dom_nau":         "bệnh đốm nâu mía",
    "Mia_benh_kham_la":         "bệnh khảm lá mía",
    "Mia_benh_ri_sat_nau":      "bệnh rỉ sắt nâu mía",
    "Mia_benh_than_den":        "bệnh than đen mía",
    "Mia_benh_thoi_hom":        "bệnh thối hom mía",
    "Mia_benh_vang_la":         "bệnh vàng lá mía",
    "Mia_khoe_manh":            "mía khỏe mạnh",
    "Mia_la_kho":               "bệnh lá khô mía",
    "Ngo_benh_chay_la_lon":     "bệnh cháy lá lớn ngô",
    "Ngo_benh_dom_la_xam":      "bệnh đốm lá xám ngô",
    "Ngo_benh_ri_sat":          "bệnh rỉ sắt ngô",
    "Ngo_khoe_manh":            "ngô khỏe mạnh",
}

# Maps CV class label → crop field value stored in Qdrant
# (matches the folder name injected by loader.py: parts[0] of relative path)
CLASS_TO_CROP: dict[str, str] = {
    "Cafe_benh_dom_rong":       "cà phê",
    "Cafe_benh_nam_ri_sat":     "cà phê",
    "Cafe_benh_phan_trang":     "cà phê",
    "Cafe_benh_phoma":          "cà phê",
    "Cafe_benh_sau_ve_bua":     "cà phê",
    "Cafe_khoe_manh":           "cà phê",
    "Lua_benh_dao_on_co_bong":  "lúa",
    "Lua_benh_dao_on_la":       "lúa",
    "Lua_benh_dom_nau":         "lúa",
    "Lua_benh_sau_gai_hispa":   "lúa",
    "Lua_benh_vang_la_tungro":  "lúa",
    "Lua_khoe_manh":            "lúa",
    "Mia_benh_choi_co":         "mía",
    "Mia_benh_dom_nau":         "mía",
    "Mia_benh_kham_la":         "mía",
    "Mia_benh_ri_sat_nau":      "mía",
    "Mia_benh_than_den":        "mía",
    "Mia_benh_thoi_hom":        "mía",
    "Mia_benh_vang_la":         "mía",
    "Mia_khoe_manh":            "mía",
    "Mia_la_kho":               "mía",
    "Ngo_benh_chay_la_lon":     "ngô",
    "Ngo_benh_dom_la_xam":      "ngô",
    "Ngo_benh_ri_sat":          "ngô",
    "Ngo_khoe_manh":            "ngô",
}


def get_vn_name(class_name: str) -> str | None:
    """Return Vietnamese disease name for a CV class label, or None."""
    return CLASS_TO_VN.get(class_name)


def get_crop(class_name: str) -> str | None:
    """Return crop key (cafe/lua/mia/ngo) for a CV class label, or None."""
    return CLASS_TO_CROP.get(class_name)


def crop_from_source(source: str) -> str:
    """Derive crop key from a knowledge file source path."""
    s = source.lower().replace("\\", "/")
    if "cà phê" in s or "/cafe" in s or "ca_phe" in s:
        return "cafe"
    if "lúa" in s or "/lua" in s:
        return "lua"
    if "mía" in s or "/mia" in s:
        return "mia"
    if "ngô" in s or "/ngo" in s:
        return "ngo"
    return "unknown"
