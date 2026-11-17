# USB: MCPX OHCI host controllers, so a title's own XAPI can find a pad

add_library(xbox_usb STATIC
    ohci.c
    usb_gamepad.c
    pad_script.c
    netplay.c
)

target_include_directories(xbox_usb PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(xbox_usb PUBLIC platform xbox_input ws2_32 winmm ole32 oleaut32 uuid)

if(MSVC)
    target_compile_options(xbox_usb PRIVATE /W4 /O2)
else()
    target_compile_options(xbox_usb PRIVATE -Wall -Wextra -O2)
endif()
