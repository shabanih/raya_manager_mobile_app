function toggleRenterFields() {
    const isRenter = document.getElementById('id_is_renter').value;
    const renterFields = document.getElementById('renter_div');

    if (isRenter === 'True') {
        renterFields.style.display = 'block';
    } else {
        renterFields.style.display = 'none';
    }
}

document.addEventListener('DOMContentLoaded', function () {
    toggleRenterFields();
    document.getElementById('id_is_renter').addEventListener('change', toggleRenterFields);
});


document.querySelector('input[name="document"]').addEventListener('change', function (event) {
    const preview = document.getElementById('preview');
    preview.innerHTML = '';

    for (let file of event.target.files) {
        const reader = new FileReader();
        reader.onload = function (e) {
            const img = document.createElement('img');
            img.src = e.target.result;
            img.classList.add('m-2');
            img.style.width = '70px';
            img.style.height = '100px';
            img.style.objectFit = 'cover';
            preview.appendChild(img);
        }
        reader.readAsDataURL(file);
    }
});


// $(document).ready(function () {
//     $("#from_date, #to_date").persianDatepicker({
//         format: 'YYYY-MM-DD',
//         autoClose: true,
//         initialValue: false,
//         observer: true, // Fix positioning
//         responsive: true, // (some forks support it, safe to include) autoClose: true,
//     });
// });

function openQuery() {
    var form = document.getElementById('query-form');
    form.style.display = (form.style.display === 'none') ? 'block' : 'none';
}


function searchTable() {
  var input = document.getElementById("searchInput");
  var filter = input.value.toLowerCase().replace(/,/g, '').replace(/\s/g, '');
  var table = document.getElementById("expenseTable");
  var rows = table.getElementsByTagName("tr");

  for (var i = 1; i < rows.length; i++) {
    var row = rows[i];
    var text = row.innerText.toLowerCase().replace(/,/g, '').replace(/\s/g, '');
    row.style.display = text.includes(filter) ? "" : "none";
  }
}

// ==================================


function searchTableIncome() {
  var input = document.getElementById("searchInput");
  var filter = input.value.toLowerCase().replace(/,/g, '').replace(/\s/g, '');
  var table = document.getElementById("incomeTable");
  var rows = table.getElementsByTagName("tr");

  for (var i = 1; i < rows.length; i++) {
    var row = rows[i];
    var text = row.innerText.toLowerCase().replace(/,/g, '').replace(/\s/g, '');
    row.style.display = text.includes(filter) ? "" : "none";
  }
}

function searchTableExpense() {
  var input = document.getElementById("searchInput");
  var filter = input.value.toLowerCase().replace(/,/g, '').replace(/\s/g, '');
  var table = document.getElementById("expenseTable");
  var rows = table.getElementsByTagName("tr");

  for (var i = 1; i < rows.length; i++) {
    var row = rows[i];
    var text = row.innerText.toLowerCase().replace(/,/g, '').replace(/\s/g, '');
    row.style.display = text.includes(filter) ? "" : "none";
  }
}
// ==============================================
function searchTableUnit() {
  var input = document.getElementById("searchInput");
  var filter = input.value.toLowerCase().replace(/,/g, '').replace(/\s/g, '');
  var table = document.getElementById("unitTable");
  var rows = table.getElementsByTagName("tr");

  for (var i = 1; i < rows.length; i++) {
    var row = rows[i];
    var text = row.innerText.toLowerCase().replace(/,/g, '').replace(/\s/g, '');
    row.style.display = text.includes(filter) ? "" : "none";
  }
}
// ===========================================================
    function searchTable() {
  var input = document.getElementById("searchInput");
  var filter = input.value.toLowerCase().replace(/,/g, '').replace(/\s/g, '');
  var table = document.getElementById("expenseTable");
  var rows = table.getElementsByTagName("tr");

  for (var i = 1; i < rows.length; i++) {
    var row = rows[i];
    var text = row.innerText.toLowerCase().replace(/,/g, '').replace(/\s/g, '');
    row.style.display = text.includes(filter) ? "" : "none";
  }
}
// ===================================================
    function searchChargeTable() {
    const input = document.getElementById('searchInput');
    const filter = input.value.toLowerCase();
    const cards = document.querySelectorAll('.fixChargeTable');

    cards.forEach(card => {
        const unitTitle = card.querySelector('.card-middleCharge-title').innerText.toLowerCase();
        const cardText = card.querySelector('.card-middleCharge-text').innerText.toLowerCase();

        if (unitTitle.includes(filter) || cardText.includes(filter)) {
            card.parentElement.style.display = '';  // کارت اصلی که col است را نشان بده
        } else {
            card.parentElement.style.display = 'none'; // کارت را مخفی کن
        }
    });
}
// ======================================

