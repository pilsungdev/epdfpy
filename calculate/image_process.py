import numpy as np
import cv2
import time
import util


try:
    import cupy as cp
    use_cupy = True
except ImportError:
    use_cupy = False

mask = util.get_mask_data()
colorcube = (np.loadtxt("./assets/colorcube256.csv", delimiter=",", dtype=np.float32) * 255).astype('int')


def draw_center_line(img, center):
    c_x, c_y = center
    c_x = int(c_x)
    c_y = int(c_y)
    rs = img.copy()
    cv2.line(rs, (c_x, 0), (c_x, rs.shape[0]), 255, 5)
    cv2.line(rs, (0, c_y), (rs.shape[1], c_y), 255, 5)
    return rs


def calculate_center(img, intensity_range, step_size):
    initial_center = _calculate_initial_center(img)
    print("initial center is ", initial_center)
    rect = _get_rectangle_from_intensity(img, intensity_range)

    #################
    find_range = 10
    #################
    evaluated_center = np.zeros((find_range * 2, find_range * 2))
    for x in range(-find_range, find_range):
        for y in range(-find_range, find_range):
            center_xy = (initial_center[0] + x, initial_center[1] + y)
            evaluated_center[x + find_range, y + find_range] = _evaluate_center_slice_range(img, center_xy, rect,
                                                                                            intensity_range, step_size)

    min_index = np.unravel_index(evaluated_center.argmin(), evaluated_center.shape)
    real_index = np.zeros(2)
    real_index[0] = min_index[0] - find_range
    real_index[1] = min_index[1] - find_range
    center = np.add(initial_center, real_index).astype('int')

    # plt.imshow(evaluated_center)
    # plt.show()
    print("calculated center is ", center)
    return center

def calculate_center_gradient(img, intensity_range, step_size):
    cost_img = np.empty(img.shape)
    cost_img[:] = np.NaN
    cursor = _calculate_initial_center(img)
    cursor = (int(cursor[0]),int(cursor[1]))
    print("initial center is ", cursor)
    rect = _get_rectangle_from_intensity(img, intensity_range)
    cnt = 0

    while(cnt < 15):
        for x in range(cursor[0]-1,cursor[0]+2):
            for y in range(cursor[1] - 1, cursor[1] + 2):
                if not np.isnan(cost_img[x, y]):
                    continue
                cost_img[x, y] = _evaluate_center_slice_range(img, (x, y), rect, intensity_range, step_size)
        if cost_img[cursor] != np.nanmin(cost_img):
            cursor = np.unravel_index(np.nanargmin(cost_img), cost_img.shape)
            cnt = cnt + 1
        else:
            return cursor

    return calculate_center(img, intensity_range, step_size)




def _calculate_initial_center(img):
    if not len(img.shape) == 2:
        raise ValueError()
    if np.array(img).min() < 0 or np.array(img).max() > 255:
        img = cv2.normalize(img,img,0,255,cv2.NORM_MINMAX)
    if img[0][0].dtype != np.uint8:
        img = img.astype(np.uint8)

    thresh = cv2.threshold(img, 0, 255, cv2.THRESH_OTSU + cv2.THRESH_BINARY)[1]  # it need uint8 as input
    kernel = np.ones((20, 20), np.uint8)
    # thresh = cv2.erode(thresh,kernel, iterations=3)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    kernel = np.ones((200, 200), np.uint8)
    # thresh = cv2.erode(thresh,kernel, iterations=3)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    thresh = np.uint8(thresh / 255)
    mesh = np.meshgrid(np.arange(thresh.shape[0]), np.arange(thresh.shape[1]))
    center_x = np.sum(mesh[0] * thresh) / np.sum(thresh)
    center_y = np.sum(mesh[1] * thresh) / np.sum(thresh)
    return center_x, center_y


def _get_rectangle_from_intensity(image, intensity_range):
    i1, i2 = intensity_range
    kernel_size = 2
    msk = cv2.inRange(image, i1, i2)
    kernel1 = np.ones((kernel_size, kernel_size), np.uint8)
    msk = cv2.erode(msk, kernel1)
    nonzero = np.nonzero(msk)
    p1_y = nonzero[0].min() - 2
    p1_x = nonzero[1].min() - 2
    p2_y = nonzero[0].max() + 2
    p2_x = nonzero[1].max() + 2
    return (p1_y, p1_x, p2_y, p2_x)


def _evaluate_center_slice_range(image, center, rect, value_range, step_size):
    center_x, center_y = center
    center_x = int(center_x)
    center_y = int(center_y)
    min_i, max_i = value_range
    shift_range = 5

    p1_y, p1_x, p2_y, p2_x = rect

    y_width_origin = p2_y - p1_y
    x_width_origin = p2_x - p1_x
    h_y_width_origin = int(y_width_origin / 2)
    h_x_width_origin = int(x_width_origin / 2)

    p1y = np.max((center_y - h_y_width_origin, 0)).astype(np.uint16)
    p2y = np.min((center_y + h_y_width_origin, image.shape[0])).astype(np.uint16)
    p1x = np.max((center_x - h_x_width_origin, 0)).astype(np.uint16)
    p2x = np.min((center_x + h_x_width_origin, image.shape[1])).astype(np.uint16)

    y_width = p2_y - p1_y
    x_width = p2_x - p1_x
    h_y_width = int(y_width / 2)
    h_x_width = int(x_width / 2)

    slc_img = image[p1y:p2y, p1x:p2x]
    slc_beam_mask = mask[p1y:p2y, p1x:p2x]

    # slc_beam_mask = beam_mask[center_y-h_y_width:center_y+h_y_width,center_x-h_x_width:center_x+h_x_width]
    slc_center_y = h_y_width
    slc_center_x = h_x_width
    slc_center_y = center_y - p1y
    slc_center_x = center_x - p1x

    if step_size > 0:
        range_ = np.linspace(min_i, max_i, step_size + 1)
    std_sum = 0
    for step in range(len(range_) - 1):
        current_min_i = int(range_[step])
        current_max_i = int(range_[step + 1])

        ring_mask = cv2.inRange(slc_img, current_min_i, current_max_i)
        ring_mask = cv2.bitwise_and(ring_mask, ring_mask, mask=(np.logical_not(slc_beam_mask) * 255).astype(np.uint8))

        mesh = np.meshgrid(range(slc_img.shape[1]), range(slc_img.shape[0]))
        mesh_y = mesh[1] - slc_center_y
        mesh_x = mesh[0] - slc_center_x

        ring_x = cv2.bitwise_and(mesh_x, mesh_x, mask=ring_mask)
        ring_y = cv2.bitwise_and(mesh_y, mesh_y, mask=ring_mask)

        dt = np.power(np.square(ring_x) + np.square(ring_y), 0.5)
        dt = dt.reshape(-1)
        std_sum += np.std(dt[np.nonzero(dt)[0]])

    return std_sum


def calculate_azimuthal_average(raw_image, center):
    if use_cupy:
        return calculate_azimuthal_average_cuda(raw_image, center)
    center_x, center_y = center
    mesh = np.meshgrid(range(raw_image.shape[1]), range(raw_image.shape[0]))
    mesh_x = mesh[0] - center_x
    mesh_y = mesh[1] - center_y
    rr = np.power(np.square(mesh_x) + np.square(mesh_y), 0.5)
    rr = cv2.bitwise_and(rr, rr, mask=np.bitwise_not(mask))
    n_rr = np.uint16(np.ceil(rr.max()))

    def vector_oper(r):
        masked_img = raw_image[(rr >= r - .5) & (rr < r + .5)]
        return masked_img.mean(), masked_img.var()

    # f = lambda r: raw_image[(rr >= r - .5) & (rr < r + .5)].mean()
    r = np.linspace(1, n_rr, num=n_rr)
    mean, var = np.vectorize(vector_oper)(r)
    mean = np.nan_to_num(mean, 0)
    var = np.nan_to_num(var, 0)

    return mean, var


def calculate_azimuthal_average_cuda(raw_image, center):
    img = cp.array(raw_image)
    beam = cp.array(mask)
    center_x, center_y = center

    mesh = cp.meshgrid(cp.arange(raw_image.shape[1]), cp.arange(raw_image.shape[0]))
    mesh_x = mesh[0] - center_x
    mesh_y = mesh[1] - center_y
    rr = cp.power(cp.square(mesh_x) + cp.square(mesh_y), 0.5)
    cp.putmask(rr, beam, 0)
    n_rr = int(cp.ceil(rr.max()))

    azav = cp.zeros((n_rr + 1))
    azvar = cp.zeros((n_rr + 1))
    for n in range(1, n_rr):
        rig_mask = (rr >= n - 0.5) & (rr < n + 0.5)
        rig = img[rig_mask]
        azav[n] = rig.mean()
        azvar[n] = rig.var()

        # rig_mask = (rr >= n - 0.5) & (rr < n + 0.5)
        # rig = img * rig_mask
        # rig = rig.reshape((-1))
        # non_zero = cp.nonzero(rig)[0]
        # ring_non_zero = rig[non_zero]
        # azav[n] = cp.average(ring_non_zero)
        # azvar[n] = cp.var(ring_non_zero)

    azav = np.nan_to_num(azav.get(), 0)
    azvar = np.nan_to_num(azvar.get(), 0)
    return azav, azvar





if __name__ == '__main__':

    import mrcfile
    from pathlib import Path
    import numpy as np
    import image_process
    import cv2

    mrc_search_path = '/mnt/experiment/TEM diffraction/'
    mrc_file_paths = [str(i) for i in Path(mrc_search_path).rglob("*.mrc")]
    random_mrc_files = np.random.choice(mrc_file_paths, 10)

    # %%

    mrc_img = mrcfile.open(random_mrc_files[0])
    raw_img = mrc_img.data
    img = np.array(raw_img)
    center = image_process.calculate_center(img, (120, 130), 10)

    # %%
    center2 = image_process.calculate_center_gradient(img, (120, 130), 10)
    print("result:",center2)