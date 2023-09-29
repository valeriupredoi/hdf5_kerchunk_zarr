import os
import numpy as np
import zarr
import ujson
import fsspec
import s3fs
import tempfile

from activestorage.config import *
from kerchunk.hdf import SingleHdf5ToZarr


def gen_json(file_url, outf, storage_type):
    """Generate a json file that contains the kerchunk-ed data for Zarr."""
    if storage_type == "s3":
        fs = s3fs.S3FileSystem(key=S3_ACCESS_KEY,
                               secret=S3_SECRET_KEY,
                               client_kwargs={'endpoint_url': S3_URL},
                               default_fill_cache=False,
                               default_cache_type="none"
        )
        fs2 = fsspec.filesystem('')
        with fs.open(file_url, 'rb') as s3file:
            h5chunks = SingleHdf5ToZarr(s3file, file_url,
                                        inline_threshold=0)
            with fs2.open(outf, 'wb') as f:
                f.write(ujson.dumps(h5chunks.translate()).encode())
    else:
        fs = fsspec.filesystem('')
        with fs.open(file_url, 'rb') as local_file:
            try:
                h5chunks = SingleHdf5ToZarr(local_file, file_url,
                                            inline_threshold=0)
            except OSError as exc:
                raiser_1 = f"Unable to open file {file_url}. "
                raiser_2 = "Check if file is netCDF3 or netCDF-classic"
                print(raiser_1 + raiser_2)
                raise exc

            # inline threshold adjusts the Size below which binary blocks are
            # included directly in the output
            # a higher inline threshold can result in a larger json file but
            # faster loading time
            # for active storage, we don't want anything inline
            with fs.open(outf, 'wb') as f:
                f.write(ujson.dumps(h5chunks.translate()).encode())

    return outf


def open_zarr_group(out_json, varname):
    """
    Do the magic opening

    Open a json file read and saved by the reference file system
    into a Zarr Group, then extract the Zarr Array you need.
    That Array is in the 'data' attribute.
    """
    fs = fsspec.filesystem("reference", fo=out_json)
    mapper = fs.get_mapper("")  # local FS mapper
    #mapper.fs.reference has the kerchunk mapping, how does this propagate into the Zarr array?
    zarr_group = zarr.open_group(mapper)
    try:
        zarr_array = getattr(zarr_group, varname)
    except AttributeError as attrerr:
        print(f"Zarr Group does not contain variable {varname}. "
              f"Zarr Group info: {zarr_group.info}")
        raise attrerr
    #print("Zarr array info:",  zarr_array.info)

    return zarr_array


def load_netcdf_zarr_generic(fileloc, varname, storage_type, build_dummy=True):
    """Pass a netCDF4 file to be shaped as Zarr file by kerchunk."""
    print(f"Storage type {storage_type}")

    # Write the Zarr group JSON to a temporary file.
    with tempfile.NamedTemporaryFile() as out_json:
        gen_json(fileloc, out_json.name, storage_type)

        # open this monster
        print(f"Attempting to open and convert {fileloc}.")
        ref_ds = open_zarr_group(out_json.name, varname)

    return ref_ds
