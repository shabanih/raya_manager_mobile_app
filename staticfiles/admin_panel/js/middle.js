$(document).on('click', '.edit-m-expense', function (e) {
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
                url: '/middle-admin-panel/expense/middle/delete-document/',  // Your delete URL
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
$(document).on('click', '.edit-m-expense', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#expenseForm').attr('action', '/middle-admin-panel/expense/middle/edit/' + id + '/');

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
    var expenseDate = $(this).data('date');
    // If the date is in a format other than YYYY-MM-DD, convert it here
    // You can use moment.js or another library for conversion if necessary
    $('#id_date').val(expenseDate);  // Assuming it's already in correct format

    $('#id_doc_no').val($(this).data('doc_no'));
    $('#id_description').val($(this).data('description'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle').text('ویرایش هزینه');
    $('#btn-submit-expense').text('ویرایش هزینه');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('expenseForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// ==========================================
$(document).on('click', '.edit-m-income', function (e) {
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
    var incomeId = $(this).data('income-id');  // Expense ID


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
                url: '/middle-admin-panel/income/middle/delete-document/',  // Your delete URL
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
 $(document).on('click', '.edit-m-income', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#incomeForm').attr('action', '/middle-admin-panel/income/middle/edit/' + id + '/');

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
     var unit = $(this).data('unit');
    if ($('#id_unit option[value="' + unit + '"]').length) {
        $('#id_unit').val(unit).trigger('change');
    }

    $('#id_payer_name').val($(this).data('payer_name'));
    $('#id_amount').val($(this).data('amount'));

    // Ensure date is in YYYY-MM-DD format before setting it
    $('#id_doc_date').val($(this).data('doc_date'));

    $('#id_doc_number').val($(this).data('doc_number'));
    $('#id_description').val($(this).data('description'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle2').text('ویرایش درآمد');
    $('#btn-submit-expense').text('ویرایش درآمد');
});
  document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('personForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// ========================================================================
$(document).on('click', '.edit-house-btn', function () {
    console.log('ویرایش کلیک شد2');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    $('#houseForm').attr('action', '/middle-admin-panel/middle/house/edit/' + id + '/');

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


 $(document).on('click', '.edit-m-bank', function () {
    console.log('ویرایش کلیک شد2');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    $('#bankForm').attr('action', '/middle-admin-panel/middle/bank/edit/' + id + '/');


    $('#id_house').val($(this).data('house')).trigger('change');
    $('#id_bank_name').val($(this).data('bank_name'));
    $('#id_account_holder_name').val($(this).data('account_holder_name'));
    $('#id_account_no').val($(this).data('account_no'));
    $('#id_sheba_number').val($(this).data('sheba_number'));
    $('#id_cart_number').val($(this).data('cart_number'));
    $('#id_initial_fund').val($(this).data('initial_fund').toString().replace(/,/g, ''));

     // ✅ set select values
    $('#id_is_active').val($(this).data('is_active'));
    $('#id_is_default').val($(this).data('is_default'));

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle3').text('ویرایش اطلاعات ساختمان');
    $('#btn-submit-bank').text('ویرایش اطلاعات ساختمان');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('bankForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

 // ==================================================
$(document).on('click', '.edit-middle-btn', function () {
    console.log('ویرایش کلیک شد2');

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
    $('#editForm select[name="is_active"]').val(isActive.toString());


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
                url: '/middle-admin-panel/receive/middle/delete-document/',  // Your delete URL
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
$(document).on('click', '.edit-Mreceive-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#receiveForm').attr('action', '/middle-admin-panel/receive/middle/edit/' + id + '/');

    // Populate the form with the expense data
    $('#id_bank').val($(this).data('bank')).trigger('change');
    $('#id_unit').val($(this).data('unit')).trigger('change');
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
                url: '/middle-admin-panel/pay/middle/delete-document/',  // Your delete URL
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
$(document).on('click', '.edit-m-pay', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#payForm').attr('action', '/middle-admin-panel/pay/middle/edit/' + id + '/');

    // Populate the form with the expense data
    $('#id_bank').val($(this).data('bank')).trigger('change');
    $('#id_unit').val($(this).data('unit')).trigger('change');
    $('#id_amount').val($(this).data('amount'));
    $('#id_receiver_name').val($(this).data('receiver_name'));
    $('#id_document_date').val($(this).data('document_date'));

    $('#id_document_number').val($(this).data('document_number'));
    $('#id_description').val($(this).data('description'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    $('#exampleModalLongTitle').text('ویرایش سند پرداختنی');
    $('#btn-submit-receive').text('ویرایش سند پرداختنی');
});
 document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('exampleModalLong');
    const form = document.getElementById('payForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });

// =============================== Property ==================
$(document).on('click', '.edit-middleProperty-btn', function (e) {
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
                url: '/middle-admin-panel/middleProperty/delete-document/',
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
                    Swal.fire('خطا', 'خطا در حذف تصویر2', 'error');
                }
            });
        }
    });
});
$(document).on('click', '.edit-middleProperty-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#propertyForm').attr('action', '/middle-admin-panel/Property/middle/edit/' + id + '/');

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
    const maintenanceId = $(this).data('maintenance-id');
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
                url: '/middle-admin-panel/maintenance/middle/delete-document/',
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
    $('#maintenanceForm').attr('action', '/middle-admin-panel/maintenance/middle/edit/' + id + '/');

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

$(document).on('click', '.edit-middleCharge-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#chargeForm').attr('action', '/middle-admin-panel/charge/middle/edit/' + id + '/');

    $('#id_name').val($(this).data('name'));
    $('#id_fix_amount').val($(this).data('fix_amount'));
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
    const form = document.getElementById('chargeForm');

    modal.addEventListener('hidden.bs.modal', function () {
      form.reset();
    });
  });


 // ==============================================
$(document).on('click', '.edit-middleCharge-area-btn', function () {
    console.log('ویرایش کلیک شد');

    // Get the expense ID from the clicked button's data attributes
    var id = $(this).data('id');
    // Set the form action URL dynamically
    $('#areaForm').attr('action', '/middle-admin-panel/area/middle/charge/edit/' + id + '/');

    $('#id_name').val($(this).data('name'));
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
    $('#personForm').attr('action', '/middle-admin-panel/person/middle/charge/edit/' + id + '/');

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
    $('#fixAreaForm').attr('action', '/middle-admin-panel/fix/area/middle/charge/edit/' + id + '/');

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
    $('#exampleModalLongTitle').text('ویرایش شارژ: ' + chargeName);
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
    $('#fixPersonForm').attr('action', '/middle-admin-panel/fix/person/middle/charge/edit/' + id + '/');

    // Set the form values based on the clicked button's data attributes
    $('#id_name').val($(this).data('name'));
    $('#id_person_amount').val($(this).data('person_amount'));
    $('#id_fix_charge_amount').val($(this).data('fix_charge_amount'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));
    $('#id_civil').val($(this).data('civil'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش شارژ: ' + chargeName);
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
    $('#personAreaForm').attr('action', '/middle-admin-panel/area/person/middle/charge/edit/' + id + '/');

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
    $('#exampleModalLongTitle').text('ویرایش شارژ: ' + chargeName);
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
    $('#FixPersonAreaForm').attr('action', '/middle-admin-panel/fix/area/person/middle/charge/edit/' + id + '/');

    // Set the form values based on the clicked button's data attributes
    $('#id_name').val($(this).data('name'));
    $('#id_fix_charge_amount').val($(this).data('fix_charge_amount'));
    $('#id_person_amount').val($(this).data('person_amount'));
    $('#id_area_amount').val($(this).data('area_amount'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));
    $('#id_civil').val($(this).data('civil'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش شارژ: ' + chargeName);
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
    $('#variableFixForm').attr('action', '/middle-admin-panel/fix/variable/middle/charge/edit/' + id + '/');

    // Set the form values based on the clicked button's data attributes
    $('#id_name').val($(this).data('name'));
    $('#id_unit_fix_amount').val($(this).data('unit_fix_amount'));
    $('#id_extra_parking_amount').val($(this).data('extra_parking_amount'));
    $('#id_unit_variable_person_amount').val($(this).data('unit_variable_person_amount'));
    $('#id_unit_variable_area_amount').val($(this).data('unit_variable_area_amount'));
    $('#id_payment_penalty_amount').val($(this).data('payment_penalty_amount'));
    $('#id_payment_deadline').val($(this).data('payment_deadline'));
    $('#id_other_cost_amount').val($(this).data('other_cost_amount'));

    $('#id_civil').val($(this).data('civil'));
    $('#id_details').val($(this).data('details'));

    // Update the modal title and submit button text for editing
    let chargeName = $(this).data('name');
    $('#exampleModalLongTitle').text('ویرایش شارژ: ' + chargeName);
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


