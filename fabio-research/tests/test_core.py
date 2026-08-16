from datetime import date
import numpy as np

from fabio_research.market import third_wednesday, front_month_expiry, front_month_expiry_at, is_monthly_expiry
from fabio_research.profile import value_area
from fabio_research.execution import _first_hit_r
from fabio_research.parquet_native import NativeParquetFile

PARQUET='/mnt/data/MTX_2025.parquet'


def test_expiry_calendar():
    assert third_wednesday(2025,1)==date(2025,1,15)
    assert front_month_expiry(date(2025,1,15))=='202501'
    assert front_month_expiry(date(2025,1,16))=='202502'
    assert front_month_expiry_at(date(2025,1,15),13*3600+29*60)=='202501'
    assert front_month_expiry_at(date(2025,1,15),13*3600+30*60)=='202502'
    assert front_month_expiry(date(2025,12,18))=='202601'


def test_spread_filter():
    assert is_monthly_expiry('202501')
    assert not is_monthly_expiry('202501W4/202502')
    assert not is_monthly_expiry('202501W4')


def test_value_area_deterministic():
    p={99:10,100:50,101:30,102:10}
    lv=value_area(p,.70)
    assert lv is not None
    assert lv.poc==100
    assert lv.val==100
    assert lv.vah==101
    assert abs(lv.total_volume-100)<1e-9


def test_first_hit_long_and_short():
    path=np.array([100,101,102,99,98],float)
    r,o,i=_first_hit_r(path,1,100,98,102,2)
    assert (r,o,i)==(1.0,'target',2)
    path2=np.array([100,99,98,101,102],float)
    r,o,i=_first_hit_r(path2,-1,100,102,98,2)
    assert (r,o,i)==(1.0,'target',2)


def test_raw_physical_order_and_side_semantics_sample():
    pf=NativeParquetFile(PARQUET)
    rg=pf.read_row_group(0,['datetime','price','side','expiry'])
    t=rg['datetime'];p=rg['price'];s=rg['side']
    assert np.all(np.diff(t)>=0)
    assert np.any(np.diff(t)==0)
    d=np.sign(np.diff(p)).astype(np.int64)
    assert np.array_equal(s[1:],d)
    assert all(isinstance(str(x), str) for x in np.unique(rg['expiry']))
