$('#myForm').on('submit', function(e){
  $('#myModal').modal('show');
  e.preventDefault();
});
// ====================
function toJalaali(gy, gm, gd) {
    var g_d_m = [0,31,59,90,120,151,181,212,243,273,304,334];
    var gy2 = (gm > 2) ? (gy + 1) : gy;
    var days = 355666 + (365 * gy) + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400) + gd + g_d_m[gm - 1];

    var jy = -1595 + (33 * Math.floor(days / 12053));
    days %= 12053;
    jy += 4 * Math.floor(days / 1461);
    days %= 1461;
    if (days > 365) {
        jy += Math.floor((days - 1)/365);
        days = (days - 1) % 365;
    }
    var jm, jd;
    if (days < 186) {
        jm = 1 + Math.floor(days/31);
        jd = 1 + (days % 31);
    } else {
        jm = 7 + Math.floor((days - 186)/30);
        jd = 1 + ((days - 186) % 30);
    }
    return {jy: jy, jm: jm, jd: jd};
}

function updateClockAndDate() {
    let now = new Date();

    // ساعت
    let hours = now.getHours().toString().padStart(2,'0');
    let minutes = now.getMinutes().toString().padStart(2,'0');
    let seconds = now.getSeconds().toString().padStart(2,'0');
    document.getElementById("time").innerHTML = "ساعت " + hours + ":" + minutes + ":" + seconds;

    // تاریخ شمسی دقیق
    let jDate = toJalaali(now.getFullYear(), now.getMonth()+1, now.getDate());
    let weekDays = ["یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنجشنبه","جمعه","شنبه"];
    let todayName = weekDays[now.getDay()];

    let jMonths = ["فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور",
                   "مهر","آبان","آذر","دی","بهمن","اسفند"];

    document.getElementById("date").innerHTML =
        "امروز: " + todayName + " " + jDate.jd + " " + jMonths[jDate.jm - 1] + " " + jDate.jy;
}

setInterval(updateClockAndDate, 1000);
updateClockAndDate();
// ======================================================

$(document).on('click', '.edit-expense-btn', function (e) {
    e.preventDefault();

    var images = $(this).data('images');
    var expenseId = $(this).data('id');  // ← گرفتن expense_id صحیح

    if (typeof images === 'string') {
        try {
            images = JSON.parse(images);
        } catch (error) {
            console.error('Error parsing images JSON:', error);
            images = [];
        }
    }

    $('#preview').empty();

    if (images.length > 0) {
        images.forEach(function(imgUrl, index) {
            var imageWrapper = `
                <div class="image-item m-2 position-relative" style="display:inline-block;">
                    <img src="${imgUrl}"
                         style="width: 100px; height: 100px; object-fit: cover; border: 1px solid #ccc;">
                    <button type="button" class="btn btn-sm btn-danger delete-image321-btn"
                            data-url="${imgUrl}"
                            data-expense-id="${expenseId}"
                            style="position: absolute; top: -5px; right: -5px; border-radius: 50%;">
                        ×
                    </button>
                </div>
            `;
            $('#preview').append(imageWrapper);
        });
    } else {
        $('#preview').html('<p>تصویری وجود ندارد.</p>');
    }
});
$(document).on('click', '.delete-image321-btn', function () {
    var imageUrl = $(this).data('url');  // Image URL
    var expenseId = $(this).data('expense-id');  // Expense ID
    console.log(expenseId)

    if (!imageUrl || !expenseId) {
        Swal.fire('خطا', 'URL یا ID هزینه مشخص نیست', 'error');
        return;
    }

    Swal.fire({
        title: 'آیا مطمئنی میخوای این تصویر رو حذف کنی؟',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'بله، حذف کن!',
        cancelButtonText: 'لغو'
    }).then((result) => {
        if (result.isConfirmed) {
            // Send the request to delete the image
            $.ajax({
                type: 'POST',
                url: '/admin-panel/expense/delete-document/',  // Your delete URL
                data: {
                    csrfmiddlewaretoken: '{{ csrf_token }}',  // Ensure CSRF token is included
                    url: imageUrl,  // The URL of the image to delete
                    expense_id: expenseId  // The ID of the related expense
                },
                success: function(response) {
                    if (response.status === 'success') {
                        Swal.fire('حذف شد!', 'تصویر با موفقیت حذف شد.', 'success');
                        // Optionally, remove the image from the preview
                        $(`[data-url="${imageUrl}"]`).closest('.image-item').remove();
                    } else {
                        Swal.fire('خطا', response.message, 'error');
                    }
                },
                error: function() {
                    Swal.fire('خطا', 'خطا در حذف تصویر', 'error');
                }
            });
        }
    });
});
$(document).on('click', '.edit-expense-btn', function () {
    console.log('ویرایش کلیک شد');

    var id = $(this).data('id');
    $('#expenseForm').attr('action', '/admin-panel/expense/edit/' + id + '/');

    // category
    var category = $(this).data('category');
    if ($('#id_category option[value="' + category + '"]').length) {
        $('#id_category').val(category).trigger('change');
    }

    // bank
    var bank = $(this).data('bank');
    if ($('#id_bank option[value="' + bank + '"]').length) {
        $('#id_bank').val(bank).trigger('change');
    }

    $('#id_amount').val($(this).data('amount'));
    $('#id_date').val($(this).data('date'));
    $('#id_doc_no').val($(this).data('doc_no'));
    $('#id_description').val($(this).data('description'));
    $('#id_details').val($(this).data('details'));

    $('#exampleModalLongTitle').text('ویرایش هزینه');
    $('#btn-submit-expense').text('ویرایش هزینه');
});

document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('expenseForm'); // ✅ اصلاح شد

    modal.addEventListener('hidden.bs.modal', function () {
        form.reset();
    });
});

// ==========================================
$(document).on('click', '.edit-income-btn', function (e) {
    e.preventDefault();

    var images = $(this).data('images');
    var incomeId = $(this).data('id');  // ← گرفتن expense_id صحیح

    if (typeof images === 'string') {
        try {
            images = JSON.parse(images);
        } catch (error) {
            console.error('Error parsing images JSON:', error);
            images = [];
        }
    }

    $('#preview').empty();

    if (images.length > 0) {
        images.forEach(function(imgUrl, index) {
            var imageWrapper = `
                <div class="image-item m-2 position-relative" style="display:inline-block;">
                    <img src="${imgUrl}"
                         style="width: 100px; height: 100px; object-fit: cover; border: 1px solid #ccc;">
                    <button type="button" class="btn btn-sm btn-danger delete-image21-btn"
                            data-url="${imgUrl}"
                            data-income-id="${incomeId}"
                            style="position: absolute; top: -5px; right: -5px; border-radius: 50%;">
                        ×
                    </button>
                </div>
            `;
            $('#preview').append(imageWrapper);
        });
    } else {
        $('#preview').html('<p>تصویری وجود ندارد.</p>');
    }
});

$(document).on('click', '.delete-image21-btn', function () {
    var imageUrl = $(this).data('url');  // Image URL
    var incomeId = $(this).data('income-id');  //


    if (!imageUrl || !incomeId) {
        Swal.fire('خطا', 'URL یا ID هزینه مشخص نیست', 'error');
        return;
    }

    Swal.fire({
        title: 'آیا مطمئنی میخوای این تصویر رو حذف کنی؟',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'بله، حذف کن!',
        cancelButtonText: 'لغو'
    }).then((result) => {
        if (result.isConfirmed) {
            // Send the request to delete the image
            $.ajax({
                type: 'POST',
                url: '/admin-panel/income/delete-document/',  // Your delete URL
                data: {
                    csrfmiddlewaretoken: '{{ csrf_token }}',  // Ensure CSRF token is included
                    url: imageUrl,  // The URL of the image to delete
                    income_id: incomeId  // The ID of the related expense
                },
                success: function(response) {
                    if (response.status === 'success') {
                        Swal.fire('حذف شد!', 'تصویر با موفقیت حذف شد.', 'success');
                        // Optionally, remove the image from the preview
                        $(`[data-url="${imageUrl}"]`).closest('.image-item').remove();
                    } else {
                        Swal.fire('خطا2', response.message, 'error');
                    }
                },
                error: function() {
                    Swal.fire('خطا', 'خطا در حذف تصویر', 'error');
                }
            });
        }
    });
});

$(document).on('click', '.edit-income-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#incomeForm').attr('action', '/admin-panel/income/edit/' + id + '/');

   // category
    var category = $(this).data('category');
    if ($('#id_category option[value="' + category + '"]').length) {
        $('#id_category').val(category).trigger('change');
    }

    // bank
    var bank = $(this).data('bank');
    if ($('#id_bank option[value="' + bank + '"]').length) {
        $('#id_bank').val(bank).trigger('change');
    }


    $('#id_amount').val($(this).data('amount'));

    // Ensure date is in YYYY-MM-DD format before setting it
    var expenseDate = $(this).data('doc_date');
    // If the date is in a format other than YYYY-MM-DD, convert it here
    // You can use moment.js or another library for conversion if necessary
    $('#id_doc_date').val(expenseDate);  // Assuming it's already in correct format

    $('#id_doc_number').val($(this).data('doc_number'));
    $('#id_description').val($(this).data('description'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle2').text('ویرایش درآمد');
    $('#btn-submit-expense').text('ویرایش درآمد');
});

document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('incomeForm'); // ✅ اصلاح شد

    modal.addEventListener('hidden.bs.modal', function () {
        form.reset();
    });
});

// ========================================
$(document).on('click', '.edit-house-btn', function () {
    console.log('ویرایش کلیک شد2');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    $('#houseForm').attr('action', '/admin-panel/house/edit/' + id + '/');

    // Populate the form with the expense data
    $('#id_name').val($(this).data('name'));
    $('#id_user_type').val($(this).data('user_type'));
    $('#id_city').val($(this).data('city'));
    $('#id_address').val($(this).data('address'));
       // تعیین مقدار is_active
    let isActive = $(this).data('is_active');
    $('#editForm select[name="is_active"]').val(isActive.toString());
    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle3').text('ویرایش اطلاعات ');
    $('#btn-submit-bank').text('ویرایش اطلاعات ساختمان');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('personForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });


 $(document).on('click', '.edit-bank-btn', function () {
    console.log('ویرایش کلیک شد2');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    $('#bankForm').attr('action', '/admin-panel/bank/edit/' + id + '/');


    $('#id_house').val($(this).data('house')).trigger('change');
    $('#id_bank_name').val($(this).data('bank_name'));
    $('#id_account_holder_name').val($(this).data('account_holder_name'));
    $('#id_account_no').val($(this).data('account_no'));
    $('#id_sheba_number').val($(this).data('sheba_number'));
    $('#id_cart_number').val($(this).data('cart_number'));
    $('#id_initial_fund').val($(this).data('initial_fund').toString().replace(/,/g, ''));
    let isActive = $(this).data('is_active');
    $('#editForm select[name="is_active"]').val(isActive.toString());

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle3').text('ویرایش اطلاعات ساختمان');
    $('#btn-submit-bank').text('ویرایش اطلاعات ساختمان');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('personForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

 // ==================================================
$(document).on('click', '.edit-middle-btn', function () {
    console.log('ویرایش کلیک شد2');

    var modal = $('#exampleModalLong3'); // ← اضافه شد

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    $('#middleForm').attr('action', '/admin-panel/middle/edit/' + id + '/');

    // Populate the form with the expense data
    $('#id_full_name').val($(this).data('full_name'));
    $('#id_mobile').val($(this).data('mobile'));
    $('#id_username').val($(this).data('username'));

    $('#middleForm input[name="password"]').val('');
    $('#middleForm input[name="confirm_password"]').val('');

    // تعیین مقدار is_active
    let isActive = $(this).data('is_active');
    $('#middleForm select[name="is_active"]').val(isActive.toString());

    // پر کردن چک‌باکس‌های charge_methods
    var selectedMethods = $(this).data('charge-methods');
    if (typeof selectedMethods === 'string') {
        selectedMethods = JSON.parse(selectedMethods);
    }
    modal.find('input[name="charge_methods"]').prop('checked', false);
    if (selectedMethods) {
        selectedMethods.forEach(function(id) {
            modal.find('input[name="charge_methods"][value="'+id+'"]').prop('checked', true);
        });
    }

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle3').text('ویرایش اطلاعات مدیر ساختمان');
    $('#btn-submit-bank').text('ویرایش اطلاعات ');
});

 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('personForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// ===================================================
$(document).on('click', '.edit-receive-btn', function (e) {
    e.preventDefault();

    var images = $(this).data('images');
    var receiveId = $(this).data('id');  //

    if (typeof images === 'string') {
        try {
            images = JSON.parse(images);
        } catch (error) {
            console.error('Error parsing images JSON:', error);
            images = [];
        }
    }

    $('#preview').empty();

    if (images.length > 0) {
        images.forEach(function(imgUrl, index) {
            var imageWrapper = `
                <div class="image-item m-2 position-relative" style="display:inline-block;">
                    <img src="${imgUrl}"
                         style="width: 100px; height: 100px; object-fit: cover; border: 1px solid #ccc;">
                    <button type="button" class="btn btn-sm btn-danger delete-image1-btn"
                            data-url="${imgUrl}"
                            data-receive-id="${receiveId}"
                            style="position: absolute; top: -5px; right: -5px; border-radius: 50%;">
                        ×
                    </button>
                </div>
            `;
            $('#preview').append(imageWrapper);
        });
    } else {
        $('#preview').html('<p>تصویری وجود ندارد.</p>');
    }
});

$(document).on('click', '.delete-image1-btn', function () {
    var imageUrl = $(this).data('url');  // Image URL
    var receiveId = $(this).data('receive-id');


    if (!imageUrl || !receiveId) {
        Swal.fire('خطا', 'URL یا ID هزینه مشخص نیست', 'error');
        return;
    }

    Swal.fire({
        title: 'آیا مطمئنی میخوای این تصویر رو حذف کنی؟',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'بله، حذف کن!',
        cancelButtonText: 'لغو'
    }).then((result) => {
        if (result.isConfirmed) {
            // Send the request to delete the image
            $.ajax({
                type: 'POST',
                url: '/admin-panel/receive/delete-document/',  // Your delete URL
                data: {
                    csrfmiddlewaretoken: '{{ csrf_token }}',  // Ensure CSRF token is included
                    url: imageUrl,  // The URL of the image to delete
                    receive_id: receiveId  // The ID of the related expense
                },
                success: function(response) {
                    if (response.status === 'success') {
                        Swal.fire('حذف شد!', 'تصویر با موفقیت حذف شد.', 'success');
                        // Optionally, remove the image from the preview
                        $(`[data-url="${imageUrl}"]`).closest('.image-item').remove();
                    } else {
                        Swal.fire('خطا2', response.message, 'error');
                    }
                },
                error: function() {
                    Swal.fire('خطا', 'خطا در حذف تصویر', 'error');
                }
            });
        }
    });
});

$(document).on('click', '.edit-receive-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#receiveForm').attr('action', '/admin-panel/receive/edit/' + id + '/');

    // Populate the form with the expense data
    $('#id_bank').val($(this).data('bank')).trigger('change');
    $('#id_amount').val($(this).data('amount'));
    $('#id_payer_name').val($(this).data('payer_name'));

    // Ensure date is in YYYY-MM-DD format before setting it
    var receiveDate = $(this).data('doc_date');
    // If the date is in a format other than YYYY-MM-DD, convert it here
    // You can use moment.js or another library for conversion if necessary
    $('#id_doc_date').val(receiveDate);  // Assuming it's already in correct format

    $('#id_doc_number').val($(this).data('doc_number'));
    $('#id_description').val($(this).data('description'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle').text('ویرایش سند دریافتنی');
    $('#btn-submit-receive').text('ویرایش سند دریافتنی');
});

 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('personForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });
// ================================================= pay ====
$(document).on('click', '.edit-pay-btn', function (e) {
    e.preventDefault();

    var images = $(this).data('images');
    var paymentId = $(this).data('id');  //

    if (typeof images === 'string') {
        try {
            images = JSON.parse(images);
        } catch (error) {
            console.error('Error parsing images JSON:', error);
            images = [];
        }
    }

    $('#preview').empty();

    if (images.length > 0) {
        images.forEach(function(imgUrl, index) {
            var imageWrapper = `
                <div class="image-item m-2 position-relative" style="display:inline-block;">
                    <img src="${imgUrl}"
                         style="width: 100px; height: 100px; object-fit: cover; border: 1px solid #ccc;">
                    <button type="button" class="btn btn-sm btn-danger delete-image_payment-btn"
                            data-url="${imgUrl}"
                            data-payment-id="${paymentId}"
                            style="position: absolute; top: -5px; right: -5px; border-radius: 50%;">
                        ×
                    </button>
                </div>
            `;
            $('#preview').append(imageWrapper);
        });
    } else {
        $('#preview').html('<p>تصویری وجود ندارد.</p>');
    }
});

$(document).on('click', '.delete-image_payment-btn', function () {
    const imageUrl = $(this).data('url');
    const paymentId = $(this).data('payment-id');
    const button = $(this);


    if (!imageUrl || !paymentId) {
        Swal.fire('خطا', 'URL یا ID هزینه مشخص نیست', 'error');
        return;
    }

    Swal.fire({
        title: 'آیا مطمئنی میخوای این تصویر رو حذف کنی؟',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'بله، حذف کن!',
        cancelButtonText: 'لغو'
    }).then((result) => {
        if (result.isConfirmed) {
            // Send the request to delete the image
            $.ajax({
                type: 'POST',
                url: '/admin-panel/pay/delete-document/',  // Your delete URL
                data: {
                    csrfmiddlewaretoken: '{{ csrf_token }}',  // Ensure CSRF token is included
                    url: imageUrl,  // The URL of the image to delete
                    payment_id: paymentId  // The ID of the related expense
                },
                success: function(response) {
                    if (response.status === 'success') {
                        Swal.fire('حذف شد!', 'تصویر با موفقیت حذف شد.', 'success');
                        button.closest('.image-item').remove();
                    } else {
                        Swal.fire('خطا', response.message, 'error');
                    }
                },
                error: function() {
                    Swal.fire('خطا', 'خطا در حذف تصویر', 'error');
                }
            });
        }
    });
});
$(document).on('click', '.edit-pay-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#receiveForm').attr('action', '/admin-panel/pay/edit/' + id + '/');

    // Populate the form with the expense data
    $('#id_bank').val($(this).data('bank')).trigger('change');
    $('#id_amount').val($(this).data('amount'));
    $('#id_receiver_name').val($(this).data('receiver_name'));

    // Ensure date is in YYYY-MM-DD format before setting it
    var receiveDate = $(this).data('document_date');
    // If the date is in a format other than YYYY-MM-DD, convert it here
    // You can use moment.js or another library for conversion if necessary
    $('#id_document_date').val(receiveDate);  // Assuming it's already in correct format

    $('#id_document_number').val($(this).data('document_number'));
    $('#id_description').val($(this).data('description'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle').text('ویرایش سند پرداختنی');
    $('#btn-submit-receive').text('ویرایش سند پرداختنی');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('personForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// =============================== Property ==================
$(document).on('click', '.edit-productProperty-btn', function (e) {
    e.preventDefault();

    var images = $(this).data('images');
    var propertyId = $(this).data('id');  //

    if (typeof images === 'string') {
        try {
            images = JSON.parse(images);
        } catch (error) {
            console.error('Error parsing images JSON:', error);
            images = [];
        }
    }

    $('#preview').empty();

    if (images.length > 0) {
        images.forEach(function(imgUrl, index) {
            var imageWrapper = `
                <div class="image-item m-2 position-relative" style="display:inline-block;">
                    <img src="${imgUrl}"
                         style="width: 100px; height: 100px; object-fit: cover; border: 1px solid #ccc;">
                    <button type="button" class="btn btn-sm btn-danger delete-image2-btn"
                            data-url="${imgUrl}"
                            data-property-id="${propertyId}"
                            style="position: absolute; top: -5px; right: -5px; border-radius: 50%;">
                        ×
                    </button>
                </div>
            `;
            $('#preview').append(imageWrapper);
        });
    } else {
        $('#preview').html('<p>تصویری وجود ندارد.</p>');
    }
});

$(document).on('click', '.delete-image2-btn', function () {
    const imageUrl = $(this).data('url');
    const propertyId = $(this).data('property-id');
    const button = $(this);  // Save reference for removal later

    if (!imageUrl || !propertyId) {
        Swal.fire('خطا', 'آدرس یا شناسه نگهداری مشخص نیست2.', 'error');
        return;
    }

    Swal.fire({
        title: 'آیا مطمئنی می‌خواهی این تصویر را حذف کنی؟',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'بله، حذف کن!',
        cancelButtonText: 'لغو'
    }).then((result) => {
        if (result.isConfirmed) {
            $.ajax({
                type: 'POST',
                url: '/admin-panel/productProperty/delete-document/',
                data: {
                    url: imageUrl,
                    property_id: propertyId
                },
                success: function(response) {
                    if (response.status === 'success') {
                        Swal.fire('حذف شد!', 'تصویر با موفقیت حذف شد.', 'success');
                        button.closest('.image-item').remove();
                    } else {
                        Swal.fire('خطا', response.message, 'error');
                    }
                },
                error: function() {
                    Swal.fire('خطا', 'خطا در حذف تصویر', 'error');
                }
            });
        }
    });
});
$(document).on('click', '.edit-productProperty-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#propertyForm').attr('action', '/admin-panel/productProperty/edit/' + id + '/');

    $('#id_property_name').val($(this).data('property_name'));
    $('#id_property_unit').val($(this).data('property_unit'));

    // Ensure date is in YYYY-MM-DD format before setting it
    var propertyDate = $(this).data('property_purchase_date');
    // If the date is in a format other than YYYY-MM-DD, convert it here
    // You can use moment.js or another library for conversion if necessary
    $('#id_property_purchase_date').val(propertyDate);  // Assuming it's already in correct format

    $('#id_property_location').val($(this).data('property_location'));
    $('#id_property_price').val($(this).data('property_price'));
    $('#id_property_code').val($(this).data('property_code'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle').text('ویرایش اموال');
    $('#btn-submit-receive').text('ویرایش اموال');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('personForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// =============================== Maintenance ==================
$(document).on('click', '.edit-maintenance-btn', function (e) {
    e.preventDefault();

    var images = $(this).data('images');
    var maintenanceId = $(this).data('id');  //

    if (typeof images === 'string') {
        try {
            images = JSON.parse(images);
        } catch (error) {
            console.error('Error parsing images JSON:', error);
            images = [];
        }
    }

    $('#preview').empty();

    if (images.length > 0) {
        images.forEach(function(imgUrl, index) {
            var imageWrapper = `
                <div class="image-item m-2 position-relative" style="display:inline-block;">
                    <img src="${imgUrl}"
                         style="width: 100px; height: 100px; object-fit: cover; border: 1px solid #ccc;">
                    <button type="button" class="btn btn-sm btn-danger delete-image-btn"
                            data-url="${imgUrl}"
                            data-maintenance-id="${maintenanceId}"
                            style="position: absolute; top: -5px; right: -5px; border-radius: 50%;">
                        ×
                    </button>
                </div>
            `;
            $('#preview').append(imageWrapper);
        });
    } else {
        $('#preview').html('<p>تصویری وجود ندارد.</p>');
    }
});

$(document).on('click', '.delete-image-btn', function () {
    const imageUrl = $(this).data('url');
    const maintenanceId = $(this).data('middleMaintenance-id');
    const button = $(this);  // Save reference for removal later

    if (!imageUrl || !maintenanceId) {
        Swal.fire('خطا', 'آدرس یا شناسه نگهداری مشخص نیست4.', 'error');
        return;
    }

    Swal.fire({
        title: 'آیا مطمئنی می‌خواهی این تصویر را حذف کنی؟',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'بله، حذف کن!',
        cancelButtonText: 'لغو'
    }).then((result) => {
        if (result.isConfirmed) {
            $.ajax({
                type: 'POST',
                url: '/admin-panel/maintenance/delete-document/',
                data: {
                    url: imageUrl,
                    maintenance_id: maintenanceId
                },
                success: function(response) {
                    if (response.status === 'success') {
                        Swal.fire('حذف شد!', 'تصویر با موفقیت حذف شد.', 'success');
                        button.closest('.image-item').remove();
                    } else {
                        Swal.fire('خطا', response.message, 'error');
                    }
                },
                error: function() {
                    Swal.fire('خطا', 'خطا در حذف تصویر', 'error');
                }
            });
        }
    });
});
$(document).on('click', '.edit-maintenance-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#maintenanceForm').attr('action', '/admin-panel/maintenance/edit/' + id + '/');

    $('#id_maintenance_description').val($(this).data('maintenance_description'));
    // Ensure date is in YYYY-MM-DD format before setting it
    var maintenanceStartDate = $(this).data('maintenance_start_date');
    var maintenanceEndDate = $(this).data('maintenance_end_date');
    // If the date is in a format other than YYYY-MM-DD, convert it here
    // You can use moment.js or another library for conversion if necessary
    $('#id_maintenance_start_date').val(maintenanceStartDate);
    $('#id_maintenance_end_date').val(maintenanceEndDate);

    $('#id_maintenance_price').val($(this).data('maintenance_price'));
    $('#id_maintenance_status').val($(this).data('maintenance_status'));
    $('#id_service_company').val($(this).data('service_company'));
    $('#id_maintenance_document_no').val($(this).data('maintenance_document_no'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle').text('ویرایش سند');
    $('#btn-submit-receive').text('ویرایش سند');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('maintenanceForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// ===================================================

$(document).on('click', '.edit-charge-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#chargeForm').attr('action', '/admin-panel/charge/edit/' + id + '/');

    $('#id_name').val($(this).data('name'));
    $('#id_fix_amount').val($(this).data('fix_amount'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));
    $('#id_civil').val($(this).data('civil'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش : ' + chargeName);
    $('#btn-submit-receive').text('ویرایش شارژ');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('chargeForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });
 // ==============================================
$(document).on('click', '.edit-charge-area-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#areaForm').attr('action', '/admin-panel/area/charge/edit/' + id + '/');

    $('#id_name').val($(this).data('name'));
    $('#id_area_amount').val($(this).data('area_amount'));
    $('#id_civil').val($(this).data('civil'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
   let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش : ' + chargeName);
    $('#btn-submit-receive').text('ویرایش شارژ');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('areaForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });


 // ==============================================
$(document).on('click', '.edit-charge-person-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#personForm').attr('action', '/admin-panel/person/charge/edit/' + id + '/');

    $('#id_name').val($(this).data('name'));
    $('#id_person_amount').val($(this).data('person_amount'));
    $('#id_civil').val($(this).data('civil'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش : ' + chargeName);
    $('#btn-submit-receive').text('ویرایش شارژ');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('personForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

 // ==============================================
// When the Edit button is clicked
$(document).on('click', '.edit-fix-area-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#fixAreaForm').attr('action', '/admin-panel/fix/area/charge/edit/' + id + '/');

    // Set the form values based on the clicked button's data attributes
    $('#id_name').val($(this).data('name'));
    $('#id_area_amount').val($(this).data('area_amount'));
    $('#id_fix_charge_amount').val($(this).data('fix_charge_amount'));
    $('#id_civil').val($(this).data('civil'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش : ' + chargeName);
    $('#btn-submit-receive').text('ویرایش شارژ');
});

  document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('fixAreaForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// ============================================================

 // ==============================================
// When the Edit button is clicked
$(document).on('click', '.edit-fix-person-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#fixPersonForm').attr('action', '/admin-panel/fix/person/charge/edit/' + id + '/');

    // Set the form values based on the clicked button's data attributes
    $('#id_name').val($(this).data('name'));
    $('#id_person_amount').val($(this).data('person_amount'));
    $('#id_fix_charge_amount').val($(this).data('fix_charge_amount'));
    $('#id_civil').val($(this).data('civil'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش : ' + chargeName);
    $('#btn-submit-receive').text('ویرایش شارژ');
});

  document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('fixPersonForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// ============================================================
$(document).on('click', '.edit-area-person-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#personAreaForm').attr('action', '/admin-panel/area/person/charge/edit/' + id + '/');

    // Set the form values based on the clicked button's data attributes
    $('#id_name').val($(this).data('name'));
    $('#id_person_amount').val($(this).data('person_amount'));
    $('#id_area_amount').val($(this).data('area_amount'));
    $('#id_civil').val($(this).data('civil'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش : ' + chargeName);
    $('#btn-submit-receive').text('ویرایش شارژ');
});

  document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('persianAreaForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// ============================================================

$(document).on('click', '.edit-area-person-fix-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#FixPersonAreaForm').attr('action', '/admin-panel/fix/area/person/charge/edit/' + id + '/');

    // Set the form values based on the clicked button's data attributes
    $('#id_name').val($(this).data('name'));
    $('#id_fix_charge_amount').val($(this).data('fix_charge_amount'));
    $('#id_person_amount').val($(this).data('person_amount'));
    $('#id_area_amount').val($(this).data('area_amount'));
    $('#id_civil').val($(this).data('civil'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش : ' + chargeName);
    $('#btn-submit-receive').text('ویرایش شارژ');
});

  document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('personAreaFixForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// ============================================================
$(document).on('click', '.edit-variable-fix-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#variableFixForm').attr('action', '/admin-panel/fix/variable/charge/edit/' + id + '/');

    // Set the form values based on the clicked button's data attributes
    $('#id_name').val($(this).data('name'));
    $('#id_unit_fix_amount').val($(this).data('unit_fix_amount'));
    $('#id_extra_parking_amount').val($(this).data('extra_parking_amount'));
    $('#id_unit_variable_person_amount').val($(this).data('unit_variable_person_amount'));
    $('#id_unit_variable_area_amount').val($(this).data('unit_variable_area_amount'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));
    $('#id_civil').val($(this).data('civil'));
    $('#id_details').val($(this).data('details'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    // Update the modal title and submit button text for editing
    let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش : ' + chargeName);
    $('#btn-submit-receive').text('ویرایش شارژ');
});

  document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('variableFixForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });
  // =======================================================
    document.addEventListener('DOMContentLoaded', function () {
        const toggleBtn = document.getElementById('toggle-select-btn');
        let allSelected = false;

        toggleBtn.addEventListener('click', function () {
            const checkboxes = document.querySelectorAll('.unit-checkbox:not(:disabled)');
            checkboxes.forEach(cb => cb.checked = !allSelected);

            allSelected = !allSelected;
            toggleBtn.textContent = allSelected ? 'لغو انتخاب همه واحدها' : 'انتخاب همه واحدها';
        });
    });

// ============================================
function confirmDeleteWithSweetAlert(event) {
    event.preventDefault(); // جلوگیری از رفتن به لینک فوری

    const url = event.currentTarget.href; // آدرس لینک

    Swal.fire({
        title: 'آیا نسبت به حذف این آیتم اطمینان دارید؟',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'بله',
        cancelButtonText: 'خیر',
        reverseButtons: true
    }).then((result) => {
        if (result.isConfirmed) {
            // اگر کاربر تأیید کرد، به لینک هدایت شود
            window.location.href = url;
        }
        // اگر لغو کرد، کاری انجام نمی‌شود
    });

    return false; // جلوگیری از رفتار پیش‌فرض لینک
}

// ================sms =================
document.addEventListener("DOMContentLoaded", function() {
    const available = document.getElementById("availableUnits");
    const selected = document.getElementById("selectedUnits");
    const addBtn = document.getElementById("addBtn");
    const removeBtn = document.getElementById("removeBtn");
    const addAllBtn = document.getElementById("addAllBtn");
    const removeAllBtn = document.getElementById("removeAllBtn");
    const searchAvailable = document.getElementById("searchAvailable");
    const searchSelected = document.getElementById("searchSelected");
    const form = document.querySelector("form");

    // انتقال گزینه‌ها
    addBtn.onclick = () => moveOptions(available, selected);
    removeBtn.onclick = () => moveOptions(selected, available);
    addAllBtn.onclick = () => moveAllOptions(available, selected);
    removeAllBtn.onclick = () => moveAllOptions(selected, available);

    function moveOptions(from, to) {
        [...from.selectedOptions].forEach(opt => {
            to.add(opt);
            opt.selected = true; // ✅ اینجا اضافه شد
        });
    }

    function moveAllOptions(from, to) {
        [...from.options].forEach(opt => {
            to.add(opt);
            opt.selected = true; // ✅ اینجا اضافه شد
        });
    }
    // جستجو
    searchAvailable.addEventListener("keyup", function() {
        const filter = this.value.toLowerCase();
        [...available.options].forEach(opt => {
            opt.style.display = opt.text.toLowerCase().includes(filter) ? "" : "none";
        });
    });

    searchSelected.addEventListener("keyup", function() {
        const filter = this.value.toLowerCase();
        [...selected.options].forEach(opt => {
            opt.style.display = opt.text.toLowerCase().includes(filter) ? "" : "none";
        });
    });

    // SweetAlert تأیید ارسال
    form.addEventListener("submit", function(e) {
        e.preventDefault();
        Swal.fire({
            title: 'ارسال پیامک؟',
            text: "آیا از ارسال پیامک برای واحدهای انتخاب‌شده اطمینان دارید؟",
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: 'بله، ارسال شود',
            cancelButtonText: 'خیر',
        }).then((result) => {
            if (result.isConfirmed) {
                [...selected.options].forEach(opt => opt.selected = true);
                form.submit();
            }
        });
    });
});



