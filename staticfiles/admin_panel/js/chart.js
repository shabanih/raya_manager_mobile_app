$(function () {
  /* ChartJS
   * -------
   * Data and config for chartjs
   */
  'use strict';
  var data = {
    labels: ["2013", "2014", "2014", "2015", "2016", "2017"],
    datasets: [{
      label: '# of Votes',
      data: [10, 19, 3, 5, 2, 3],
      backgroundColor: [
        'rgba(255, 99, 132, 0.2)',
        'rgba(54, 162, 235, 0.2)',
        'rgba(255, 206, 86, 0.2)',
        'rgba(75, 192, 192, 0.2)',
        'rgba(153, 102, 255, 0.2)',
        'rgba(255, 159, 64, 0.2)'
      ],
      borderColor: [
        'rgba(255,99,132,1)',
        'rgba(54, 162, 235, 1)',
        'rgba(255, 206, 86, 1)',
        'rgba(75, 192, 192, 1)',
        'rgba(153, 102, 255, 1)',
        'rgba(255, 159, 64, 1)'
      ],
      borderWidth: 1,
      fill: false
    }]
  };
  var multiLineData = {
    labels: ["Red", "Blue", "Yellow", "Green", "Purple", "Orange"],
    datasets: [{
      label: 'Dataset 1',
      data: [12, 19, 3, 5, 2, 3],
      borderColor: [
        '#587ce4'
      ],
      borderWidth: 2,
      fill: false
    },
    {
      label: 'Dataset 2',
      data: [5, 23, 7, 12, 42, 23],
      borderColor: [
        '#ede190'
      ],
      borderWidth: 2,
      fill: false
    },
    {
      label: 'Dataset 3',
      data: [15, 10, 21, 32, 12, 33],
      borderColor: [
        '#f44252'
      ],
      borderWidth: 2,
      fill: false
    }
    ]
  };
  var options = {
    scales: {
      y: {
        ticks: {
          beginAtZero: true
        }
      }
    },
    legend: {
      display: false
    },
    elements: {
      line: {
        tension: 0.5
      },
      point: {
        radius: 0
      }
    }

  };
  var doughnutPieData = {
    datasets: [{
      data: [20, 90, 10],
      backgroundColor: [
        'rgba(255, 99, 132, 0.5)',
        'rgba(54, 162, 235, 0.5)',
        'rgba(255, 206, 86, 0.5)',
        'rgba(75, 192, 192, 0.5)',
        'rgba(153, 102, 255, 0.5)',
        'rgba(255, 159, 64, 0.5)'
      ],
      borderColor: [
        'rgba(255,99,132,1)',
        'rgba(54, 162, 235, 1)',
        'rgba(255, 206, 86, 1)',
        'rgba(75, 192, 192, 1)',
        'rgba(153, 102, 255, 1)',
        'rgba(255, 159, 64, 1)'
      ],
    }],

    // These labels appear in the legend and in the tooltips when hovering different arcs
    labels: [
      'Pink',
      'Blue',
      'Yellow',
    ]
  };
  var doughnutPieOptions = {
    responsive: true,
    animation: {
      animateScale: true,
      animateRotate: true
    }
  };
  var areaData = {
    labels: ["2013", "2014", "2015", "2016", "2017"],
    datasets: [{
      label: '# of Votes',
      data: [12, 19, 3, 5, 2, 3],
      backgroundColor: [
        'rgba(255, 99, 132, 0.2)',
        'rgba(54, 162, 235, 0.2)',
        'rgba(255, 206, 86, 0.2)',
        'rgba(75, 192, 192, 0.2)',
        'rgba(153, 102, 255, 0.2)',
        'rgba(255, 159, 64, 0.2)'
      ],
      borderColor: [
        'rgba(255,99,132,1)',
        'rgba(54, 162, 235, 1)',
        'rgba(255, 206, 86, 1)',
        'rgba(75, 192, 192, 1)',
        'rgba(153, 102, 255, 1)',
        'rgba(255, 159, 64, 1)'
      ],
      borderWidth: 1,
      fill: true, // 3: no fill
    }]
  };

  var areaOptions = {
    elements: {
      line: {
        tension: 0.5
      }
    },
    plugins: {
      filler: {
        propagate: true
      }
    }
  }

  var multiAreaData = {
    labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    datasets: [{
      label: 'Facebook',
      data: [8, 11, 13, 15, 12, 13, 16, 15, 13, 19, 11, 14],
      borderColor: ['rgba(255, 99, 132, 0.5)'],
      backgroundColor: ['rgba(255, 99, 132, 0.5)'],
      borderWidth: 1,
      fill: true
    },
    {
      label: 'Twitter',
      data: [7, 17, 12, 16, 14, 18, 16, 12, 15, 11, 13, 9],
      borderColor: ['rgba(54, 162, 235, 0.5)'],
      backgroundColor: ['rgba(54, 162, 235, 0.5)'],
      borderWidth: 1,
      fill: true
    },
    {
      label: 'Linkedin',
      data: [6, 14, 16, 20, 12, 18, 15, 12, 17, 19, 15, 11],
      borderColor: ['rgba(255, 206, 86, 0.5)'],
      backgroundColor: ['rgba(255, 206, 86, 0.5)'],
      borderWidth: 1,
      fill: true
    }
    ]
  };

  var multiAreaOptions = {
    plugins: {
      filler: {
        propagate: true
      }
    },
    elements: {
      line: {
        tension: 0.5
      },
      point: {
        radius: 0
      }
    },
    scales: {
      x: {
        gridLines: {
          display: false
        }
      },
      y: {
        gridLines: {
          display: false
        }
      }
    }
  }

  var scatterChartData = {
    datasets: [{
      label: 'First Dataset',
      data: [{
        x: -10,
        y: 0
      },
      {
        x: 0,
        y: 3
      },
      {
        x: -25,
        y: 5
      },
      {
        x: 40,
        y: 5
      }
      ],
      backgroundColor: [
        'rgba(255, 99, 132, 0.2)'
      ],
      borderColor: [
        'rgba(255,99,132,1)'
      ],
      borderWidth: 1
    },
    {
      label: 'Second Dataset',
      data: [{
        x: 10,
        y: 5
      },
      {
        x: 20,
        y: -30
      },
      {
        x: -25,
        y: 15
      },
      {
        x: -10,
        y: 5
      }
      ],
      backgroundColor: [
        'rgba(54, 162, 235, 0.2)',
      ],
      borderColor: [
        'rgba(54, 162, 235, 1)',
      ],
      borderWidth: 1
    }
    ]
  }

  var scatterChartOptions = {
    scales: {
      x: {
        type: 'linear',
        position: 'bottom'
      }
    }
  }
  // Get context with jQuery - using jQuery's .get() method.
  if ($("#barChart").length) {
    var barChartCanvas = $("#barChart").get(0).getContext("2d");
    // This will get the first returned node in the jQuery collection.
    var barChart = new Chart(barChartCanvas, {
      type: 'bar',
      data: data,
      options: options
    });
  }

  if ($("#lineChart").length) {
    var lineChartCanvas = $("#lineChart").get(0).getContext("2d");
    var lineChart = new Chart(lineChartCanvas, {
      type: 'line',
      data: data,
      options: options
    });
  }

  if ($("#linechart-multi").length) {
    var multiLineCanvas = $("#linechart-multi").get(0).getContext("2d");
    var lineChart = new Chart(multiLineCanvas, {
      type: 'line',
      data: multiLineData,
      options: options
    });
  }

  if ($("#areachart-multi").length) {
    var multiAreaCanvas = $("#areachart-multi").get(0).getContext("2d");
    var multiAreaChart = new Chart(multiAreaCanvas, {
      type: 'line',
      data: multiAreaData,
      options: multiAreaOptions
    });
  }

  if ($("#doughnutChart").length) {
    var doughnutChartCanvas = $("#doughnutChart").get(0).getContext("2d");
    var doughnutChart = new Chart(doughnutChartCanvas, {
      type: 'doughnut',
      data: doughnutPieData,
      options: doughnutPieOptions
    });
  }

  if ($("#pieChart").length) {
    var pieChartCanvas = $("#pieChart").get(0).getContext("2d");
    var pieChart = new Chart(pieChartCanvas, {
      type: 'pie',
      data: doughnutPieData,
      options: doughnutPieOptions
    });
  }

  if ($("#areaChart").length) {
    var areaChartCanvas = $("#areaChart").get(0).getContext("2d");
    var areaChart = new Chart(areaChartCanvas, {
      type: 'line',
      data: areaData,
      options: areaOptions
    });
  }

  if ($("#scatterChart").length) {
    var scatterChartCanvas = $("#scatterChart").get(0).getContext("2d");
    var scatterChart = new Chart(scatterChartCanvas, {
      type: 'scatter',
      data: scatterChartData,
      options: scatterChartOptions
    });
  }

  if ($("#browserTrafficChart").length) {
    var doughnutChartCanvas = $("#browserTrafficChart").get(0).getContext("2d");
    var doughnutChart = new Chart(doughnutChartCanvas, {
      type: 'doughnut',
      data: browserTrafficData,
      options: doughnutPieOptions
    });
  }
});

// ============================================================


window.addEventListener("DOMContentLoaded", function () {

    const persianMonthNames = [
        "فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور",
        "مهر","آبان","آذر","دی","بهمن","اسفند"
    ];

    const monthSelect = document.getElementById("monthSelect");
    const yearSelect = document.getElementById("yearSelect");
    const prevBtn = document.getElementById("prevMonthBtn");
    const nextBtn = document.getElementById("nextMonthBtn");
    const todayBtn = document.getElementById("gotoTodayBtn");

    const noteModal = document.getElementById("noteModal");
    const noteText = document.getElementById("noteText");
    const selectedDayTitle = document.getElementById("selectedDayTitle");
    const saveNoteBtn = document.getElementById("saveNoteBtn");
    const closeNoteBtn = document.getElementById("closeNoteBtn");
    const deleteNoteBtn = document.getElementById("deleteNoteBtn");

    let selectedYear, selectedMonth, selectedDay;

    const todayParts = new Intl.DateTimeFormat("fa-IR-u-nu-latn", {
        year: "numeric", month: "numeric", day: "numeric", calendar: "persian"
    }).formatToParts(new Date());

    let currentYear = parseInt(todayParts.find(p => p.type === "year").value);
    let currentMonth = parseInt(todayParts.find(p => p.type === "month").value);
    let currentDay = parseInt(todayParts.find(p => p.type === "day").value);

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    const csrftoken = getCookie('csrftoken');

    // سلکت‌ها
    persianMonthNames.forEach((name,i)=>{ monthSelect.appendChild(new Option(name,i+1)); });
    for(let y=currentYear-5;y<=currentYear+5;y++){ yearSelect.appendChild(new Option(y,y)); }
    monthSelect.value=currentMonth; yearSelect.value=currentYear;

    async function renderCalendar(){
        const tbody=document.querySelector("#calendar tbody");
        tbody.innerHTML="";

        // گرفتن نوت‌ها از سرور
        let notes = {};
        try{
            const res = await fetch(`/admin-panel/calendar/notes/${currentYear}/${currentMonth}/`);
            notes = await res.json();
            console.log("Notes from server:", notes);
        }catch(e){ console.error(e); }

        const daysInMonth = new Date(currentYear, currentMonth<=6?currentMonth:currentMonth+1,0).getDate();
        const firstDayGregorian = new Date(currentYear, currentMonth-1,1);
        const weekDay = (firstDayGregorian.getDay()+1)%7;

        let row = document.createElement("tr");
        for(let i=0;i<weekDay;i++){ row.appendChild(document.createElement("td")); }

        for(let d=1; d<=daysInMonth; d++){
            if(row.children.length===7){ tbody.appendChild(row); row=document.createElement("tr"); }

            const td=document.createElement("td");
            td.textContent=d;

            const noteKey = String(d);

            if(notes[noteKey]) {
                td.classList.add("has-note");

                // اضافه کردن پیش‌نمایش نوت
                const preview = document.createElement("div");
                preview.classList.add("note-preview");
                // نمایش فقط 8 کاراکتر اول
                preview.textContent = notes[noteKey].length > 13 ? notes[noteKey].substring(0,8) + "…" : notes[noteKey];
                td.appendChild(preview);
            }

            if(d===currentDay && currentMonth===parseInt(todayParts.find(p=>p.type==='month').value)
               && currentYear===parseInt(todayParts.find(p=>p.type==='year').value)){
                td.classList.add("today");
            }

            td.onclick=()=>{
                selectedYear=currentYear;
                selectedMonth=currentMonth;
                selectedDay=d;
                selectedDayTitle.textContent=`یادداشت ${d} ${persianMonthNames[currentMonth-1]}`;
                noteText.value=notes[noteKey] || "";
                noteModal.style.display="flex";
            };

            row.appendChild(td);
        }


        if(row.children.length>0) tbody.appendChild(row);
    }

    function saveNote(){
        const noteValue = noteText.value.trim();
        fetch('/admin-panel/calendar/save-note/', {
            method:'POST',
            headers:{'Content-Type':'application/json','X-CSRFToken':csrftoken},
            body:JSON.stringify({year:selectedYear,month:selectedMonth,day:selectedDay,note:noteValue})
        }).then(()=>{ noteModal.style.display="none"; renderCalendar(); });
    }

    function deleteNote(){
        fetch('/admin-panel/calendar/delete-note/', {
            method:'POST',
            headers:{'Content-Type':'application/json','X-CSRFToken':csrftoken},
            body:JSON.stringify({year:selectedYear,month:selectedMonth,day:selectedDay})
        }).then(()=>{ noteModal.style.display="none"; renderCalendar(); });
    }

    saveNoteBtn.addEventListener("click", saveNote);
    deleteNoteBtn.addEventListener("click", deleteNote);
    closeNoteBtn.addEventListener("click",()=>{ noteModal.style.display="none"; });

    prevBtn.addEventListener("click",()=>{
        currentMonth--; if(currentMonth<1){ currentMonth=12; currentYear--; }
        monthSelect.value=currentMonth; yearSelect.value=currentYear;
        renderCalendar();
    });
    nextBtn.addEventListener("click",()=>{
        currentMonth++; if(currentMonth>12){ currentMonth=1; currentYear++; }
        monthSelect.value=currentMonth; yearSelect.value=currentYear;
        renderCalendar();
    });
    todayBtn.addEventListener("click",()=>{
        currentYear=parseInt(todayParts.find(p=>p.type==='year').value);
        currentMonth=parseInt(todayParts.find(p=>p.type==='month').value);
        monthSelect.value=currentMonth; yearSelect.value=currentYear;
        renderCalendar();
    });
    monthSelect.addEventListener("change",()=>{ currentMonth=parseInt(monthSelect.value); renderCalendar(); });
    yearSelect.addEventListener("change",()=>{ currentYear=parseInt(yearSelect.value); renderCalendar(); });

    renderCalendar();
});


